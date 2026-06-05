import asyncio
import time
import os
import threading

# Імітуємо об'єкт PPO моделі
class DummyModel:
    def __init__(self, version_id):
        self.version_id = version_id

class NeocortexActor:
    def __init__(self):
        self.model = DummyModel("v0")
        self.max_latency_ms = 0.0

    async def hot_reload_model(self, checkpoint_path):
        """Завантажує модель асинхронно, щоб не блокувати Event Loop."""
        def load_heavy_model():
            # Симуляція важкої операції torch.load() та десеріалізації (500 мс)
            time.sleep(0.5) 
            with open(checkpoint_path, 'r') as f:
                version = f.read().strip()
            return DummyModel(version)
        
        # Виконуємо синхронну (важку) функцію у фоновому потоці пулу asyncio
        new_model = await asyncio.to_thread(load_heavy_model)
        
        # Атомарна підміна вказівника (у Python присвоєння об'єкта є атомарним завдяки GIL)
        self.model = new_model
        print(f"\n[Watcher] 🔄 Model hot-reloaded to {self.model.version_id} successfully.")

class ExperimentSim:
    def __init__(self):
        self.actor = NeocortexActor()
        self.running = True
        self.checkpoint_file = "dummy_checkpoint.pt"
        self.tick_interval = 0.01  # 10 ms

    async def actor_loop(self):
        """Симулює високочастотний цикл обробки FSM-подій."""
        print(f"[Actor] Starting high-frequency event loop ({self.tick_interval*1000:.0f}ms tick)...")
        last_tick = time.perf_counter()
        
        while self.running:
            await asyncio.sleep(self.tick_interval)
            now = time.perf_counter()
            
            # Розрахунок затримки (скільки часу ми були заблоковані понад очікувані 10мс)
            latency_ms = (now - last_tick - self.tick_interval) * 1000 
            
            # Фільтруємо дрібний системний шум
            if latency_ms > 0:
                if latency_ms > self.actor.max_latency_ms:
                    self.actor.max_latency_ms = latency_ms
                    
                if latency_ms > 20: # Спайк > 20мс - це вже аномалія
                    print(f"[Actor] ⚠️ LATENCY SPIKE DETECTED: {latency_ms:.2f} ms")
                
            last_tick = now

    async def watcher_loop(self):
        """Симулює фоновий процес, що моніторить появу нових чекпоінтів від Learner-а."""
        last_mtime = 0
        while self.running:
            await asyncio.sleep(0.5)
            if os.path.exists(self.checkpoint_file):
                mtime = os.path.getmtime(self.checkpoint_file)
                if mtime > last_mtime:
                    last_mtime = mtime
                    print(f"\n[Watcher] 📥 New checkpoint detected on disk. Starting background load...")
                    # Очікуємо завершення фонового завантаження, АЛЕ це не блокує actor_loop
                    await self.actor.hot_reload_model(self.checkpoint_file)

    def learner_simulator(self):
        """Симулює Offline Learner (працює в окремому OS потоці/процесі)."""
        time.sleep(2)
        print("\n[Learner] 💾 Training complete. Saving new checkpoint v1...")
        with open(self.checkpoint_file, 'w') as f:
            f.write("v1")
            
        time.sleep(2)
        print("\n[Learner] 💾 Training complete. Saving new checkpoint v2...")
        with open(self.checkpoint_file, 'w') as f:
            f.write("v2")
            
        time.sleep(2)
        self.running = False # Зупиняємо експеримент

    async def run(self):
        # Створюємо базовий файл
        with open(self.checkpoint_file, 'w') as f:
            f.write("v0")
            
        # Запускаємо симулятор Learner-а в реальному фоновому потоці OS
        threading.Thread(target=self.learner_simulator, daemon=True).start()
        
        # Запускаємо Actor і Watcher конкурентно в одному Event Loop
        await asyncio.gather(
            self.actor_loop(),
            self.watcher_loop()
        )
        
        print("\n--- Simulation Complete ---")
        print(f"Final Model Version active in Actor: {self.actor.model.version_id}")
        print(f"Max Event Loop Blocked Latency: {self.actor.max_latency_ms:.2f} ms")
        print(f"Theoretical Heavy Load Duration: 500.00 ms")
        
        if self.actor.max_latency_ms < 25.0:
            print("✅ SUCCESS: Actor-Learner Separation is viable. Heavy disk I/O and deserialization did NOT block the Event Loop.")
        else:
            print("❌ FAILURE: Event loop was blocked by model loading. Need multi-processing or Redis IPC.")
            
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)

if __name__ == "__main__":
    asyncio.run(ExperimentSim().run())
