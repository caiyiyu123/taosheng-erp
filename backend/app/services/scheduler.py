from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.models.shop import Shop
from app.services.sync import sync_shop_orders, sync_shop_inventory, sync_shop_ads, sync_shop_products
from app.config import SYNC_INTERVAL_MINUTES

scheduler = BackgroundScheduler()


def sync_all_shops():
    db = SessionLocal()
    try:
        shops = db.query(Shop).filter(Shop.is_active == True).all()
        for shop in shops:
            try:
                cards = sync_shop_orders(db, shop)
                sync_shop_inventory(db, shop)
                sync_shop_ads(db, shop, cards=cards)
                sync_shop_products(db, shop, cards=cards)
                print(f"[Scheduler] Synced shop: {shop.name}")
            except Exception as e:
                print(f"[Scheduler] Error syncing shop {shop.name}: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(sync_all_shops, "interval", minutes=SYNC_INTERVAL_MINUTES, id="sync_all")
    scheduler.start()
    print(f"[Scheduler] Started — syncing every {SYNC_INTERVAL_MINUTES} minutes")


def stop_scheduler():
    scheduler.shutdown(wait=False)
