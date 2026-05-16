# ТЕСТОВЫЙ bot.py — замените весь файл временно
import asyncio
from aiohttp import web

async def handle(request):
    return web.Response(text="OK")

async def on_startup(app):
    print("✅ Тестовый сервер запущен")

async def on_shutdown(app):
    print("🔚 Тестовый сервер остановлен")

async def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    app.router.add_get('/webhook', handle)
    app.router.add_post('/webhook', handle)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    print("🌐 Слушаю порт 8080...")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
