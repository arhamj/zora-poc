import math
import time
from eth_typing import HexStr
from web3 import Web3
import json

from zora_poc.lens_state import PoolState, Tick


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


def fetch_all_ticks(name: str, pool_address: HexStr) -> list[Tick]:
    try:
        result = lens_contract.functions.getAllTicks(pool_address).call()
        ticks = [Tick(tick[0], tick[1], tick[2]) for tick in result]
        return ticks
    except Exception as e:
        print(f"Error fetching all ticks for {name}: {e}")
        return []


TICK_BASE = 1.0001
TICK_SPACING = 200  # 0.01% fee tier
WETH_ADDRESS = "0x4200000000000000000000000000000000000006"


def get_liquidity(ticks_net_liquidity_mapping: dict) -> None:
    # fetch all the state variables
    tick_spacing = TICK_SPACING
    token0 = pool_contract.functions.token0().call()
    token1 = pool_contract.functions.token1().call()
    decimals0, decimals1 = 18, 18

    slot0 = pool_contract.functions.slot0().call()
    current_tick = slot0[1]

    current_liquidity = pool_contract.functions.liquidity().call()

    print(f"Tick spacing: {tick_spacing}")
    print(f"Token0: {token0}, Token1: {token1}")
    print(f"Decimals0: {decimals0}, Decimals1: {decimals1}")
    print(f"Current tick: {current_tick}")
    print(f"Current liquidity: {current_liquidity}")

    # calculations
    liquidity = 0

    # boundaries
    min_tick = min(ticks_net_liquidity_mapping.keys())
    max_tick = max(ticks_net_liquidity_mapping.keys())
    print(f"Min tick: {min_tick}, Max tick: {max_tick}")

    # find the tick range
    current_range_bottom_tick = math.floor(current_tick / tick_spacing) * tick_spacing
    current_price = tick_to_price(current_tick)
    adjusted_current_price = current_price / (10 ** (decimals1 - decimals0))

    total_amount0 = 0
    total_amount1 = 0

    if token0 == WETH_ADDRESS:
        invert_price = True
    else:
        invert_price = False

    tick = min_tick
    while tick <= max_tick:
        liquidity_delta = tick_liquidity_net_mapping.get(tick, 0)
        liquidity += liquidity_delta

        price = tick_to_price(tick)
        adjusted_price = price / (10 ** (decimals1 - decimals0))  # 1
        if invert_price:
            adjusted_price = 1 / adjusted_price
            tokens = "{} for {}".format(token0, token1)
        else:
            tokens = "{} for {}".format(token1, token0)

        should_print_tick = liquidity != 0
        if should_print_tick:
            print(
                "ticks=[{}, {}], bottom tick price={:.6f} {}".format(
                    tick, tick + tick_spacing, adjusted_price, tokens
                )
            )
        # Compute square roots of prices corresponding to the bottom and top ticks
        bottom_tick = tick
        top_tick = bottom_tick + tick_spacing
        sa = tick_to_price(bottom_tick // 2)  # sqrt price of bottom tick
        sb = tick_to_price(top_tick // 2)  # sqrt price of top tick

        if tick < current_range_bottom_tick:
            # Compute the amounts of tokens potentially in the range
            amount1 = liquidity * (sb - sa)
            amount0 = amount1 / (sb * sa)

            # Only token1 locked
            total_amount1 += amount1

            if should_print_tick:
                adjusted_amount0 = amount0 / (10**decimals0)
                adjusted_amount1 = amount1 / (10**decimals1)
                print(
                    "        {:.2f} {} locked, potentially worth {:.2f} {}".format(
                        adjusted_amount1, token1, adjusted_amount0, token0
                    )
                )

        elif tick == current_range_bottom_tick:
            # Always print the current tick. It normally has both assets locked
            print("        Current tick, both assets present!")
            print(
                "        Current price={:.6f} {}".format(
                    (
                        1 / adjusted_current_price
                        if invert_price
                        else adjusted_current_price
                    ),
                    tokens,
                )
            )

            # Print the real amounts of the two assets needed to be swapped to move out of the current tick range
            current_sqrt_price = tick_to_price(current_tick / 2)
            amount0actual = (
                liquidity * (sb - current_sqrt_price) / (current_sqrt_price * sb)
            )
            amount1actual = liquidity * (current_sqrt_price - sa)
            adjusted_amount0actual = amount0actual / (10**decimals0)
            adjusted_amount1actual = amount1actual / (10**decimals1)

            total_amount0 += amount0actual
            total_amount1 += amount1actual

            print(
                "        {:.2f} {} and {:.2f} {} remaining in the current tick range".format(
                    adjusted_amount0actual, token0, adjusted_amount1actual, token1
                )
            )

        else:
            # Compute the amounts of tokens potentially in the range
            amount1 = liquidity * (sb - sa)
            amount0 = amount1 / (sb * sa)

            # Only token0 locked
            total_amount0 += amount0

            if should_print_tick:
                adjusted_amount0 = amount0 / (10**decimals0)
                adjusted_amount1 = amount1 / (10**decimals1)
                print(
                    "        {:.2f} {} locked, potentially worth {:.2f} {}".format(
                        adjusted_amount0, token0, adjusted_amount1, token1
                    )
                )

        tick += tick_spacing

    print(
        "In total: {:.2f} {} and {:.2f} {}".format(
            total_amount0 / 10**decimals0, token0, total_amount1 / 10**decimals1, token1
        )
    )


def swap_quote_token0_to_token1(
    amount_in: int, ticks_net_liquidity_mapping: dict, pool_state: PoolState
) -> int:
    tick_spacing = TICK_SPACING

    current_tick = pool_state.current_tick
    current_liquidity = pool_state.current_liquidity

    max_tick = max(ticks_net_liquidity_mapping.keys())

    current_range_bottom_tick = math.floor(current_tick / tick_spacing) * tick_spacing
    amount_in_remaining = amount_in * (1 - 0.0001)  # 0.01% fee
    total_token1_out = 0

    current_sqrt_price = tick_to_price(current_tick / 2)
    sqrt_price_next = tick_to_price((current_range_bottom_tick + tick_spacing) / 2)

    # Partial tick of the current range
    if amount_in_remaining > 0:
        delta_y = current_liquidity * (sqrt_price_next - current_sqrt_price)
        delta_x = delta_y / (sqrt_price_next * current_sqrt_price)

        if amount_in_remaining >= delta_x:
            total_token1_out += delta_y
            amount_in_remaining -= delta_x
        else:
            delta_y_partial = amount_in_remaining * sqrt_price_next * current_sqrt_price
            total_token1_out += delta_y_partial
            return int(total_token1_out)  # Stop early

    # Rest of the ticks
    tick = current_range_bottom_tick + tick_spacing
    while amount_in_remaining > 0 and tick <= max_tick:
        liquidity_delta = ticks_net_liquidity_mapping.get(tick, 0)
        current_liquidity += liquidity_delta

        sqrt_price_current = tick_to_price(tick / 2)
        sqrt_price_next = tick_to_price((tick + tick_spacing) / 2)

        delta_y = current_liquidity * (sqrt_price_next - sqrt_price_current)
        delta_x = delta_y / (sqrt_price_next * sqrt_price_current)

        if amount_in_remaining >= delta_x:
            total_token1_out += delta_y
            amount_in_remaining -= delta_x
        else:
            delta_y_partial = amount_in_remaining * sqrt_price_current * sqrt_price_next
            total_token1_out += delta_y_partial
            break

        tick += tick_spacing

    return int(total_token1_out)


def fetch_pool_state() -> PoolState:
    try:
        slot0 = pool_contract.functions.slot0().call()
        current_tick = slot0[1]
        current_liquidity = pool_contract.functions.liquidity().call()
        return PoolState(current_tick, current_liquidity)
    except Exception as e:
        print(f"Error fetching pool state: {e}")
        return PoolState(0, 0)


def swap_quote_token1_to_token0(
    amount_in: int, ticks_net_liquidity_mapping: dict, pool_state: PoolState
) -> int:
    tick_spacing = TICK_SPACING
    current_tick = pool_state.current_tick
    current_liquidity = pool_state.current_liquidity

    min_tick = min(ticks_net_liquidity_mapping.keys())

    current_range_bottom_tick = math.floor(current_tick / tick_spacing) * tick_spacing
    amount_in_remaining = amount_in * (1 - 0.0001)  # 0.01% fee
    total_token0_out = 0

    current_sqrt_price = tick_to_price(current_tick / 2)
    sqrt_price_previous = tick_to_price(current_range_bottom_tick / 2)

    # Partial tick of the current range
    if amount_in_remaining > 0:
        delta_x = current_liquidity * (1 / sqrt_price_previous - 1 / current_sqrt_price)
        delta_y = delta_x * current_sqrt_price * sqrt_price_previous

        if amount_in_remaining >= delta_y:
            total_token0_out += delta_x
            amount_in_remaining -= delta_y
        else:
            delta_x_partial = amount_in_remaining / (
                current_sqrt_price * sqrt_price_previous
            )
            total_token0_out += delta_x_partial
            return int(total_token0_out)  # Stop early

    # Rest of the ticks
    tick = current_range_bottom_tick
    while amount_in_remaining > 0 and tick >= min_tick:
        liquidity_delta = ticks_net_liquidity_mapping.get(tick, 0)
        current_liquidity += liquidity_delta

        sqrt_price_current = tick_to_price(tick / 2)
        sqrt_price_previous = tick_to_price((tick - tick_spacing) / 2)

        delta_x = current_liquidity * (1 / sqrt_price_previous - 1 / sqrt_price_current)
        delta_y = delta_x * sqrt_price_current * sqrt_price_previous

        if amount_in_remaining >= delta_y:
            total_token0_out += delta_x
            amount_in_remaining -= delta_y
        else:
            delta_x_partial = amount_in_remaining / (
                sqrt_price_current * sqrt_price_previous
            )
            total_token0_out += delta_x_partial
            break

        tick -= tick_spacing

    return int(total_token0_out)


def tick_to_price(tick):
    return TICK_BASE**tick


if __name__ == "__main__":
    start_time = time.time()
    ticks = fetch_all_ticks("WETH-Bowling", POOL_ADDRESS)
    print(f"Fetched {len(ticks)} ticks")
    for tick in ticks:
        print(tick)
    tick_liquidity_net_mapping = {tick.tick_index: tick.liquidity_net for tick in ticks}
    end_time = time.time()
    print(f"Execution time: {end_time - start_time} seconds")

    token0 = pool_contract.functions.token0().call()
    token1 = pool_contract.functions.token1().call()
    print(f"Token0: {token0}, Token1: {token1}")
    print("Decimals0: 18, Decimals1: 18")

    # Fetch pool state
    start_time = time.time()
    pool_state = fetch_pool_state()
    end_time = time.time()
    print(f"Pool state fetched: {pool_state}")
    print(f"Execution time: {end_time - start_time} seconds")

    print("Starting swap quote calculation (token0 to token1)...")
    amount = 100 * 10 ** (18)  # just to explain the logic
    zero_for_one = True
    start_time = time.time()
    amount_out = swap_quote_token0_to_token1(
        amount, tick_liquidity_net_mapping, pool_state
    )
    end_time = time.time()
    print(f"Amount out: {amount_out}")
    print(f"Execution time: {(end_time - start_time)*10**3} milliseconds")
    print("Swap quote calculation completed.")

    print("Starting swap quote calculation (token1 to token0)...")
    amount = 100000000 * 10**18
    zero_for_one = True
    start_time = time.time()
    amount_out = swap_quote_token1_to_token0(
        amount, tick_liquidity_net_mapping, pool_state
    )
    end_time = time.time()
    print(f"Amount out: {amount_out}")
    print(f"Execution time: {(end_time - start_time)*10**6} milliseconds")
    print("Swap quote calculation completed.")
