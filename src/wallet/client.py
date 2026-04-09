"""UpMoltWork API client with retry logic."""

import httpx
import asyncio
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type, RetryError
from pydantic import BaseModel
from src.config.loader import AegisConfig
from src.wallet.vault import vault


class BidResult(BaseModel):
    """Result from placing a bid."""
    bid_id: str
    status: str
    price_points: int
    estimated_minutes: int


class SubmissionResult(BaseModel):
    """Result from submitting a deliverable."""
    submission_id: str
    status: str


class BalanceResult(BaseModel):
    """Result from getting balance."""
    balance_points: float
    balance_usdc: float


class UpMoltWorkAPIError(Exception):
    """Raised when UpMoltWork API returns an error."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API error {status_code}: {message}")


def _get_base_url() -> str:
    """Get API base URL."""
    return "https://api.upmoltwork.mingles.ai/v1"


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(multiplier=1, min=1, max=16, jitter=1),
    retry=retry_if_exception_type((httpx.HTTPError, ConnectionError)),
    reraise=True
)
async def _make_request(method: str, path: str, config: AegisConfig, json_body: dict = None) -> dict:
    """Make HTTP request with retry logic.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., /tasks)
        config: Application config (for API key via vault)
        json_body: Optional JSON body for POST requests

    Returns:
        Parsed JSON response

    Raises:
        UpMoltWorkAPIError: For non-retryable errors (401, 402, etc.)
        RetryError: After 5 failed attempts
    """
    api_key = vault.load_upmoltwork_key()
    url = f"{_get_base_url()}{path}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            if method == "GET":
                response = await client.get(url, headers=headers, timeout=30)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=json_body, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # Handle error status codes
            if response.status_code == 401:
                raise UpMoltWorkAPIError(401, "API authentication failed — check UPMOLTWORK_API_KEY")
            elif response.status_code == 402:
                raise UpMoltWorkAPIError(402, "Insufficient balance")
            elif response.status_code >= 400:
                response.raise_for_status()

            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 402):
                raise UpMoltWorkAPIError(e.response.status_code, str(e))
            # Other errors: retry
            raise


async def place_bid(task_id: str, price_points: int, estimated_minutes: int,
                    proposed_approach: str, config: AegisConfig) -> BidResult:
    """Place bid on UpMoltWork task.

    POST /tasks/{taskId}/bids

    Args:
        task_id: UpMoltWork task ID
        price_points: Bid amount in points
        estimated_minutes: Estimated completion time (from LLM heuristic)
        proposed_approach: LLM-generated approach description
        config: Application config

    Returns:
        BidResult with bid details

    Raises:
        UpMoltWorkAPIError: If API returns error
        RetryError: After 5 failed attempts
    """
    result = await _make_request("POST", f"/tasks/{task_id}/bids", config, json_body={
        "price_points": price_points,
        "estimated_minutes": estimated_minutes,
        "proposed_approach": proposed_approach,
    })

    return BidResult(
        bid_id=result.get("id", "unknown"),
        status="placed",
        price_points=price_points,
        estimated_minutes=estimated_minutes,
    )


async def submit_result(task_id: str, result_content: str = None,
                        result_url: str = None, notes: str = None,
                        config: AegisConfig = None) -> SubmissionResult:
    """Submit deliverable for task.

    POST /tasks/{taskId}/submit

    Args:
        task_id: UpMoltWork task ID
        result_content: Deliverable content (for single-file deliverables)
        result_url: URL to deliverable (Gist/repo for larger projects)
        notes: Optional submission notes
        config: Application config

    Returns:
        SubmissionResult with submission details

    Raises:
        UpMoltWorkAPIError: If API returns error
        RetryError: After 5 failed attempts
    """
    body = {}
    if result_content:
        body["result_content"] = result_content
    if result_url:
        body["result_url"] = result_url
    if notes:
        body["notes"] = notes

    result = await _make_request("POST", f"/tasks/{task_id}/submit", config, json_body=body)

    return SubmissionResult(
        submission_id=result.get("id", "unknown"),
        status="submitted",
    )


async def get_balance(config: AegisConfig) -> BalanceResult:
    """Get current points and USDC balance.

    GET /points/balance

    Args:
        config: Application config

    Returns:
        BalanceResult with current balances

    Raises:
        UpMoltWorkAPIError: If API returns error
        RetryError: After 5 failed attempts
    """
    result = await _make_request("GET", "/points/balance", config)

    return BalanceResult(
        balance_points=result.get("balance_points", 0),
        balance_usdc=result.get("balance_usdc", 0),
    )


async def estimate_time(task_description: str, config: AegisConfig) -> int:
    """Estimate task duration using LLM-as-estimator.

    Calls LLM 3 times and returns average of estimates.

    Args:
        task_description: Task description from UpMoltWork
        config: Application config

    Returns:
        Estimated minutes as integer
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=vault.load_openrouter_key(),
        base_url="https://openrouter.ai/api/v1"
    )

    estimates = []
    for _ in range(3):
        prompt = (
            f"Estimate the time in minutes to complete this task: {task_description}. "
            f"Consider complexity, code size. Return integer only."
        )
        try:
            response = await client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
            )
            text = response.choices[0].message.content.strip()
            estimate = int(''.join(filter(str.isdigit, text)) or "60")
            estimates.append(estimate)
        except Exception:
            # Fallback: use 60 minutes as default
            estimates.append(60)

    avg_estimate = sum(estimates) / len(estimates)
    return int(avg_estimate)


async def main():
    """Test mode: call API endpoints."""
    from src.config.loader import load_config

    print("Testing wallet client...")

    try:
        config = await load_config()

        # Test get_balance
        print("Calling get_balance()...")
        balance = await get_balance(config)
        print(f"✓ Balance: {balance.balance_points} points, {balance.balance_usdc} USDC")

        # Test estimate_time
        print("\nCalling estimate_time()...")
        minutes = await estimate_time("Write a Python CLI tool", config)
        print(f"✓ Estimated time: {minutes} minutes (3-call average)")

    except Exception as e:
        print(f"✗ Error: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
