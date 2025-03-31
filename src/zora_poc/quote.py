from decimal import Decimal
import json
import math
from typing import Tuple
from web3 import Web3

sorted_ticks = [-199200, 887200]

liquidity_map = {-199200: 46803509475895271139383, 887200: 46803509475895271139383}

Q96 = 2**96


# Configuration
RPC_URL = "http://base-proxy.lat.nodes.internal.notnotzora.com"
POOL_ADDRESS = Web3.to_checksum_address("0x280a628e91f29ae8dca3e9b32e4d540b38ccb13a")
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


# Compute sqrtPriceX96 from a tick
def tick_to_sqrt_price(tick: int) -> int:
    return int(Decimal(1.0001) ** (Decimal(tick) / 2) * Decimal(2**96))


def sqrt_price_to_tick(sqrt_price_x96: int) -> int:
    price = Decimal(sqrt_price_x96) ** 2 / Decimal(2**192)
    # Tick is log base 1.0001 of price
    tick = math.floor(math.log(float(price), 1.0001))
    return tick


def compute_swap_step_for_token0_to_token1(
    sqrt_price_x96: int,
    target_sqrt_price_x96: int,
    liquidity: int,
    amount_remaining: int,
    fee_pips: int,
) -> Tuple[int, int, int, int]:
    fee_factor = 1000000 - fee_pips
    amount_remaining_less_fee = (amount_remaining * fee_factor) // 1000000
    sqrt_price_next_x96 = max(
        target_sqrt_price_x96,
        sqrt_price_x96
        - (sqrt_price_x96 * amount_remaining_less_fee)
        // (liquidity * fee_factor + amount_remaining_less_fee),
    )

    sqrt_price_next_x96 = max(sqrt_price_next_x96, target_sqrt_price_x96)

    # Calculate amounts based on price change
    amount_in = liquidity * abs(sqrt_price_x96 - sqrt_price_next_x96) // Q96
    amount_out = (
        liquidity
        * abs(sqrt_price_x96 - sqrt_price_next_x96)
        // sqrt_price_x96
        // sqrt_price_next_x96
    )
    print(
        f"abs: {sqrt_price_next_x96}"
    )
    print(f"amount_in: {amount_in}, amount_out: {amount_out}")

    # Apply fee
    fee_amount = amount_remaining - amount_in

    return sqrt_price_next_x96, amount_in, amount_out, fee_amount

# token0 to token1 
def get_quote_for_token0_to_token1(amount0: int) -> int:
    if amount0 <= 0:
        return 0

    # Get the current state of the pool
    slot0 = pool_contract.functions.slot0().call() # rpc call 1
    sqrt_price_x96 = slot0[0]
    current_tick = slot0[1]
    current_tick_index = sorted_ticks.index(current_tick) - 1

    liquidity = pool_contract.functions.liquidity().call() # rpc call 2
    amount_remaining = amount0

    sqrt_price_limit_x96 = 2
    assert sqrt_price_limit_x96 < sqrt_price_x96, "Price limit already exceeded"
    amount_out = 0
    fee = pool_contract.functions.fee().call()

    while amount_remaining > 0 and sqrt_price_x96 != sqrt_price_limit_x96:
        next_tick_index = current_tick_index + 1
        if next_tick_index >= len(sorted_ticks):
            break
        next_tick = sorted_ticks[next_tick_index]
        sqrt_price_next_x96 = tick_to_sqrt_price(next_tick)
        print(f"sqrt_price_next_x96: {sqrt_price_next_x96}")
        sqrt_price_next_x96 = min(sqrt_price_next_x96, sqrt_price_limit_x96)
        sqrt_price_x96, amount_in_step, amount_out_step, fee_amount = (
            compute_swap_step_for_token0_to_token1(
                sqrt_price_x96, sqrt_price_next_x96, liquidity, amount_remaining, fee
            )
        )

        amount_remaining -= amount_in_step + fee_amount
        amount_out += amount_out_step

        if sqrt_price_x96 == sqrt_price_next_x96:
            current_tick = next_tick

            # Update liquidity if tick has net liquidity change
            if next_tick in liquidity_map:
                delta = liquidity_map[next_tick]
                liquidity -= delta
        else:
            current_tick = sqrt_price_to_tick(sqrt_price_x96)
    return amount_out


def main():
    amount0 = 46803509475895271139385
    amount1 = get_quote_for_token0_to_token1(amount0)
    print(f"Amount of token1 that can be obtained: {amount1}")


if __name__ == "__main__":
    main()
