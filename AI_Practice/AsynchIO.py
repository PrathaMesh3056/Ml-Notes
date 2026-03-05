import asyncio

sem = asyncio.Semaphore(3)

async def tool_web_search(query:str) -> str:
    async with sem:
        await asyncio.sleep(1)
        return f"agent tool_web_search:{query}"
    
async def calculator(expr:str) -> str:
    async with sem:
        await asyncio.sleep(0.8)
        result = eval(expr)            # ✅ actually evaluates "2+2" → 4
        return f"result of: {result}"  

async def db_lookup(key:str) -> str:
    async with sem:
        await asyncio.sleep(0.5)
        return f"db lookup :{key}"
    
async def run_agent(user_input:str) -> str:
    print(f"Agent received : {user_input}")

    tasks=[]
    async with asyncio.TaskGroup() as tg:
        tasks.append(tg.create_task(tool_web_search(user_input)))
        tasks.append(tg.create_task(calculator("2+2")))
        tasks.append(tg.create_task(db_lookup(user_input)))

    for i,t in enumerate (tasks,1):
        print (f"Tool {i} result:{t.result()}")

asyncio.run(run_agent("python asyncio"))