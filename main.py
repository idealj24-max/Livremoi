import math
import uuid
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Livremoi API - Mauritanie")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- BASE DE DONNÉES EN MÉMOIRE ---
CITIES_DB = {
    "nouakchott": {
        "name": "Nouakchott",
        "center": [18.0858, -15.9785],
        "zoom": 13,
        "restaurants": [
            {
                "id": 1, "name": "Le Sultan", "zone": "Tevragh-Zeina",
                "lat": 18.0965, "lng": -15.9890,
                "menu": [
                    {"id": 101, "name": "Chawarma Poulet + Frites", "price": 180},
                    {"id": 102, "name": "Méchoui d'Agneau", "price": 450},
                    {"id": 103, "name": "Jus de Bissap Frais", "price": 50}
                ]
            },
            {
                "id": 2, "name": "Chez Mama Thieb", "zone": "Capitale / Ksar",
                "lat": 18.0820, "lng": -15.9720,
                "menu": [
                    {"id": 201, "name": "Thieboudienne Rouge Royal", "price": 200},
                    {"id": 202, "name": "Yassa Poulet Citronné", "price": 220}
                ]
            }
        ],
        "drivers": [
            {"id": "D1", "name": "Sidi Mohamed (Moto)", "lat": 18.0910, "lng": -15.9810, "available": True},
            {"id": "D2", "name": "Oumar Ba (Scooter)", "lat": 18.0780, "lng": -15.9750, "available": True}
        ]
    },
    "nouadhibou": {
        "name": "Nouadhibou",
        "center": [20.9310, -17.0347],
        "zoom": 13,
        "restaurants": [
            {
                "id": 4, "name": "La Perle de la Baie", "zone": "Cansado",
                "lat": 20.9150, "lng": -17.0320,
                "menu": [{"id": 401, "name": "Daurade Grillée du Port", "price": 350}]
            }
        ],
        "drivers": [{"id": "D3", "name": "Brahim (Moto)", "lat": 20.9320, "lng": -17.0350, "available": True}]
    },
    "zouerat": {
        "name": "Zouérat",
        "center": [22.7354, -12.4713],
        "zoom": 14,
        "restaurants": [
            {
                "id": 5, "name": "Resto Kedia", "zone": "Cité SNIM",
                "lat": 22.7380, "lng": -12.4750,
                "menu": [{"id": 501, "name": "Brochettes de Chameau", "price": 250}]
            }
        ],
        "drivers": [{"id": "D4", "name": "Lemrabott (Moto)", "lat": 22.7340, "lng": -12.4700, "available": True}]
    },
    "kiffa": {
        "name": "Kiffa",
        "center": [16.6207, -11.4021],
        "zoom": 14,
        "restaurants": [
            {
                "id": 6, "name": "Carrefour Assaba", "zone": "Centre Kiffa",
                "lat": 16.6220, "lng": -11.4010,
                "menu": [{"id": 601, "name": "Riz à la Viande", "price": 180}]
            }
        ],
        "drivers": [{"id": "D5", "name": "Abdallahi (Moto)", "lat": 16.6190, "lng": -11.4040, "available": True}]
    },
    "atar": {
        "name": "Atar",
        "center": [20.5177, -13.0486],
        "zoom": 14,
        "restaurants": [
            {
                "id": 7, "name": "Oasis Adrar", "zone": "Marché Central",
                "lat": 20.5190, "lng": -13.0490,
                "menu": [{"id": 701, "name": "Tajine d'Agneau aux Dattes", "price": 320}]
            }
        ],
        "drivers": [{"id": "D6", "name": "Mohamed Vall (Moto)", "lat": 20.5160, "lng": -13.0470, "available": True}]
    }
}

ORDERS_DB: List[dict] = []
PLATFORM_STATS = {"total_commission": 0.0, "total_deliveries": 0}

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

class MenuItemCreate(BaseModel):
    city: str
    resto_id: int
    name: str
    price: int

class OrderCreate(BaseModel):
    city: str
    resto_id: int
    items: List[dict]
    total: int
    client_lat: float
    client_lng: float
    landmark: str
    payment_method: str
    phone_number: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/state")
async def get_initial_state():
    return {"cities": CITIES_DB, "orders": ORDERS_DB, "stats": PLATFORM_STATS}

@app.post("/api/menu/add")
async def add_menu_item(payload: MenuItemCreate):
    city = CITIES_DB.get(payload.city)
    if not city:
        return {"error": "Ville introuvable"}
    for resto in city["restaurants"]:
        if resto["id"] == payload.resto_id:
            new_item = {"id": int(uuid.uuid4().int >> 96), "name": payload.name, "price": payload.price}
            resto["menu"].append(new_item)
            await manager.broadcast({"type": "STATE_UPDATE", "cities": CITIES_DB, "orders": ORDERS_DB, "stats": PLATFORM_STATS})
            return {"status": "ok", "item": new_item}
    return {"error": "Restaurant introuvable"}

@app.delete("/api/menu/{city_key}/{resto_id}/{item_id}")
async def delete_menu_item(city_key: str, resto_id: int, item_id: int):
    city = CITIES_DB.get(city_key)
    if city:
        for resto in city["restaurants"]:
            if resto["id"] == resto_id:
                resto["menu"] = [i for i in resto["menu"] if i["id"] != item_id]
                await manager.broadcast({"type": "STATE_UPDATE", "cities": CITIES_DB, "orders": ORDERS_DB, "stats": PLATFORM_STATS})
                return {"status": "deleted"}
    return {"error": "Introuvable"}

@app.post("/api/orders")
async def create_order(order: OrderCreate):
    city = CITIES_DB.get(order.city)
    resto = next((r for r in city["restaurants"] if r["id"] == order.resto_id), None)
    
    delivery_fee = 150
    commission = delivery_fee * 0.14  # 14% pour l'application (21 MRU)
    driver_earnings = delivery_fee - commission  # 129 MRU pour le livreur

    # Simulation de statut de paiement automatique
    payment_status = "PAID_ONLINE" if order.payment_method in ["Bankily", "Masrvi"] else "PENDING_CASH"

    new_order = {
        "id": str(uuid.uuid4())[:6].upper(),
        "city": order.city,
        "resto": resto,
        "items": order.items,
        "total": order.total,
        "delivery_fee": delivery_fee,
        "commission": commission,
        "driver_earnings": driver_earnings,
        "client_lat": order.client_lat,
        "client_lng": order.client_lng,
        "landmark": order.landmark,
        "payment_method": order.payment_method,
        "phone_number": order.phone_number,
        "payment_status": payment_status,
        "status": "PENDING_RESTO",
        "driver": None
    }
    ORDERS_DB.insert(0, new_order)
    await manager.broadcast({"type": "STATE_UPDATE", "cities": CITIES_DB, "orders": ORDERS_DB, "stats": PLATFORM_STATS})
    return new_order

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "RESTO_ACCEPT_ORDER":
                order_id = data.get("order_id")
                for o in ORDERS_DB:
                    if o["id"] == order_id:
                        city = CITIES_DB[o["city"]]
                        nearest = min(
                            city["drivers"],
                            key=lambda d: math.hypot(d["lat"] - o["resto"]["lat"], d["lng"] - o["resto"]["lng"])
                        )
                        o["driver"] = nearest
                        o["status"] = "ASSIGNED_DRIVER"
                        break
                await manager.broadcast({"type": "STATE_UPDATE", "cities": CITIES_DB, "orders": ORDERS_DB, "stats": PLATFORM_STATS})

            elif action == "RESTO_REJECT_ORDER":
                order_id = data.get("order_id")
                for o in ORDERS_DB:
                    if o["id"] == order_id:
                        o["status"] = "REJECTED"
                        break
                await manager.broadcast({"type": "STATE_UPDATE", "cities": CITIES_DB, "orders": ORDERS_DB, "stats": PLATFORM_STATS})

            elif action == "UPDATE_ORDER_STATUS":
                order_id = data.get("order_id")
                new_status = data.get("status")
                for o in ORDERS_DB:
                    if o["id"] == order_id:
                        if new_status == "DELIVERED" and o["status"] != "DELIVERED":
                            PLATFORM_STATS["total_commission"] += o["commission"]
                            PLATFORM_STATS["total_deliveries"] += 1
                        o["status"] = new_status
                        break
                await manager.broadcast({"type": "STATE_UPDATE", "cities": CITIES_DB, "orders": ORDERS_DB, "stats": PLATFORM_STATS})

            elif action == "DRIVER_GPS_UPDATE":
                city_key = data.get("city")
                driver_id = data.get("driver_id")
                lat, lng = data.get("lat"), data.get("lng")
                
                city = CITIES_DB.get(city_key)
                if city:
                    for d in city["drivers"]:
                        if d["id"] == driver_id:
                            d["lat"], d["lng"] = lat, lng
                    for o in ORDERS_DB:
                        if o["driver"] and o["driver"]["id"] == driver_id:
                            o["driver"]["lat"], o["driver"]["lng"] = lat, lng

                await manager.broadcast({
                    "type": "GPS_TICK",
                    "city": city_key,
                    "driver_id": driver_id,
                    "lat": lat,
                    "lng": lng
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
