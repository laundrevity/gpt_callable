from agent import Agent
import asyncio


async def main():
    agent = Agent()

    print(agent.FUNCTIONS)

    answer = await agent.get_gpt_response(input('> '))

    print(answer)

if __name__ == '__main__':
    asyncio.run(main())
