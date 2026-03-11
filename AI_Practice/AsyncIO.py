
import sys 
import asyncio
from loguru import logger

logger.remove()
#logger.add(sys.stdout,format="{time:HH:mm:ss}|{level}|{message}")
logger.add(sys.stdout, serialize=True)
logger.add("agent.log",rotation="1 MB")

sem = asyncio.Semaphore(3)

async def tool_web_search(query:str) -> str:
    logger.info(f"Tool Started: web_search | input:{query}")
    async with sem:
        await asyncio.sleep(1)
        return f"agent tool_web_search:{query}"
    logger.success(f"Tool Done: web_search")
    
async def calculator(expr:str) -> str:
    logger.info(f"Tool Started: Calculator| input :{expr}")
    async with sem:
        await asyncio.sleep(0.8)
        result = eval(expr)            #  actually evaluates "2+2" → 4
        return f"result of: {result}"  
    logger.success(f"Tool Done : Calculator | Result : {result}")

async def db_lookup(key:str) -> str:
    logger.info(f"Tool Started : db_lookup | input :{key}")
    async with sem:
        await asyncio.sleep(0.5)
        return f"db lookup :{key}"
    logger.success(f"Tool Done : db_lookup")
    
async def run_agent(user_input:str) -> str:
    logger.info(f"Agent Starting | input: {user_input}")
    tasks=[]
    async with asyncio.TaskGroup() as tg:
        tasks.append(tg.create_task(tool_web_search(user_input)))
        tasks.append(tg.create_task(calculator("2+2")))
        tasks.append(tg.create_task(db_lookup(user_input)))

    for i,t in enumerate (tasks,1):
       logger.info(f"Tool{i} result : {t.result()}")

logger.success("Agent completed all tools")     

asyncio.run(run_agent("python asyncio"))