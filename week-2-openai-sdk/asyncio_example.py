import asyncio

async def fetch_data(name, delay):
    print(f"Fetching data for {name}...")
    await asyncio.sleep(delay)
    print(f"Data for {name} fetched.")
    return f"Data of {name}"
    

async def main():
    tasks = [
        fetch_data("Alice", 2),
        fetch_data("Bob", 3),
        fetch_data("Charlie", 1)
    ]
    results = await asyncio.gather(*tasks)
    print("All data fetched:", results)


asyncio.run(main())