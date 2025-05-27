import asyncio
import signal
from services.sync_service import AsyncService

STOP = False

def handler_stop(*_):
    global STOP
    STOP = True

async def run_periodic(interval_sec: int = 900):
    async_service = AsyncService()
    while not STOP:
        print("[SYNC] Lanzando sincronización Holded → Cegid …")
        try:
            await async_service.fetch_holded_accounts(apply_offset=True)
        except Exception as exc:
            print("[ERROR] sincronizando:", exc)
        # espera con cancelación elegante
        for _ in range(interval_sec):
            if STOP:
                break
            await asyncio.sleep(1)

def main():
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handler_stop)
    loop.run_until_complete(run_periodic())

if __name__ == "__main__":
    main()