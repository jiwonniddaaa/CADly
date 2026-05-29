import httpx
from app.core.config import AI_AGENT_URL

async def send_to_agent(message: str):

    async with httpx.AsyncClient(timeout=60.0) as client:

        response = await client.post(
            f"{AI_AGENT_URL}/agent",
            json={
                "message": message
            }
        )

        response.raise_for_status()

        return response.json()