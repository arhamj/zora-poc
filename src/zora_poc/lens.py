import time
from eth_typing import HexStr
from web3 import Web3
import json


# Configuration
RPC_URL = "http://base-proxy.lat.nodes.internal.notnotzora.com"
LENS_ADDRESS = Web3.to_checksum_address("0x3b9eb662131aAFa7703675CD7EdBB215dBC829b4")
POOL_ADDRESS = Web3.to_checksum_address("0xE020E67Cb76C780329d4c205578Aaa6d6478Fb2A")
UNISWAP_V3_LENS_ABI_PATH = "src/zora_poc/UniswapV3Lens.json"
UNISWAP_V3_POOL_ABI_PATH = "src/zora_poc/UniswapV3Pool.json"

# Web3 setup
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise Exception("Failed to connect to Ethereum node")

# Load Uniswap V3 Pool ABI
with open(UNISWAP_V3_POOL_ABI_PATH, "r") as abi_file:
    uniswap_v3_pool_abi = json.load(abi_file)

# Contract setup
pool_contract = w3.eth.contract(address=POOL_ADDRESS, abi=uniswap_v3_pool_abi)

# Web3 setup
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise Exception("Failed to connect to Ethereum node")

# Load Uniswap V3 Pool ABI
with open(UNISWAP_V3_LENS_ABI_PATH, "r") as abi_file:
    uniswap_v3_lens_abi = json.load(abi_file)

lens_contract = w3.eth.contract(address=LENS_ADDRESS, abi=uniswap_v3_lens_abi)


class Tick:
    def __init__(self, tick_index: int, liquidity_gross: int, liquidity_net: int):
        self.tick_index = tick_index
        self.liquidity_gross = liquidity_gross
        self.liquidity_net = liquidity_net

    def __repr__(self):
        return f"Tick(tick_index={self.tick_index}, liquidity_gross={self.liquidity_gross}, liquidity_net={self.liquidity_net})"


def fetch_all_ticks(name: str, pool_address: HexStr) -> list[Tick]:
    try:
        result = lens_contract.functions.getAllTicks(pool_address).call()
        ticks = [Tick(tick[0], tick[1], tick[2]) for tick in result]
        return ticks
    except Exception as e:
        print(f"Error fetching all ticks for {name}: {e}")
        return []


def swap_quote(
    amount: int, zero_for_one: bool, ticks_gross_liquidity_mapping: dict
) -> int:
    amount_specified_remaining = amount
    slot0 = pool_contract.functions.slot0().call()
    sqrt_price_x96 = slot0[0]  # Current sqrt price of the pool
    tick = slot0[1]  # Current tick
    liquidity = (
        pool_contract.functions.liquidity().call()
    )  # Total liquidity in the pool
    amount_out = 0

    while amount_specified_remaining != 0:
        # Get the next tick based on swap direction
        if zero_for_one:
            next_tick = tick - 1  # Move down in price
        else:
            next_tick = tick + 1  # Move up in price

        # Fetch liquidity at the next tick
        liquidity_at_tick = ticks_gross_liquidity_mapping.get(next_tick, 0)
        if liquidity_at_tick == 0:
            break  # No more liquidity available

        # Calculate the price difference between the current and next tick
        sqrt_next_price_x96 = get_sqrt_price_from_tick(next_tick)

        # Calculate the amount we can swap before reaching the next tick
        delta_liquidity = liquidity_at_tick - liquidity
        max_amount_in_tick = (sqrt_next_price_x96 - sqrt_price_x96) * delta_liquidity

        if abs(amount_specified_remaining) >= abs(max_amount_in_tick):
            # Fully consume this tick's liquidity
            amount_out += max_amount_in_tick
            amount_specified_remaining -= max_amount_in_tick
            sqrt_price_x96 = sqrt_next_price_x96
            tick = next_tick
        else:
            # Partially consume this tick's liquidity
            amount_out += amount_specified_remaining
            sqrt_price_x96 += amount_specified_remaining / delta_liquidity
            amount_specified_remaining = 0

    return amount_out


def get_sqrt_price_from_tick(tick: int) -> int:
    """
    Uniswap V3 sqrtPrice = 1.0001^tick * 2^96.
    """
    tick_squared = 1.0001**tick
    sqrt_price = int(tick_squared * (2**96))
    return sqrt_price


if __name__ == "__main__":
    start_time = time.time()
    ticks = fetch_all_ticks("WETH-Bowling", POOL_ADDRESS)
    print(f"Fetched {len(ticks)} ticks")
    for tick in ticks:
        print(tick)
    tick_gross_liquidity_mapping = {
        tick.tick_index: tick.liquidity_gross for tick in ticks
    }
    end_time = time.time()
    print(f"Execution time: {end_time - start_time} seconds")

    print("Starting swap quote calculation...")
    amount = 1000000000000000000
    zero_for_one = True
    start_time = time.time()
    amount_out = swap_quote(amount, zero_for_one, tick_gross_liquidity_mapping)
    end_time = time.time()
    print(f"Amount out: {amount_out}")
    print(f"Execution time: {end_time - start_time} seconds")
    print("Swap quote calculation completed.")
