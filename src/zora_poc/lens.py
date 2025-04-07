from dataclasses import dataclass
import math
import time
from eth_typing import HexStr
from web3 import Web3
import json

from zora_poc.lens_state import PoolState, Tick
from zora_poc.simulator.libraries import (
    FullMath,
    LiquidityMath,
    SafeMath,
    TickMath,
    Tick as LibTick,
)
from zora_poc.simulator.libraries import SwapMath
from zora_poc.simulator.libraries.Shared import (
    MAX_SQRT_RATIO,
    MIN_SQRT_RATIO,
    FixedPoint128_Q128,
    checkInputTypes,
    toUint256,
)


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

    # calculations
    liquidity = 0

    # boundaries
    min_tick = min(ticks_net_liquidity_mapping.keys())
    max_tick = max(ticks_net_liquidity_mapping.keys())

    # find the tick range
    current_range_bottom_tick = math.floor(current_tick / tick_spacing) * tick_spacing

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

        elif tick == current_range_bottom_tick:
            # Print the real amounts of the two assets needed to be swapped to move out of the current tick range
            current_sqrt_price = tick_to_price(current_tick / 2)
            amount0actual = (
                liquidity * (sb - current_sqrt_price) / (current_sqrt_price * sb)
            )
            amount1actual = liquidity * (current_sqrt_price - sa)

            total_amount0 += amount0actual
            total_amount1 += amount1actual

        else:
            # Compute the amounts of tokens potentially in the range
            amount1 = liquidity * (sb - sa)
            amount0 = amount1 / (sb * sa)

            # Only token0 locked
            total_amount0 += amount0

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


def swap_quote_token0_to_token1_2(
    amount_in: int, ticks_net_liquidity_mapping: dict, pool_state: PoolState
) -> int:
    tick_spacing = TICK_SPACING
    current_tick = pool_state.current_tick
    current_liquidity = pool_state.current_liquidity

    max_tick = max(ticks_net_liquidity_mapping.keys())

    current_range_bottom_tick = math.floor(current_tick / tick_spacing) * tick_spacing
    amount_in_remaining = amount_in
    total_token1_out = 0
    tick = current_range_bottom_tick

    while amount_in_remaining > 0 and tick <= max_tick:
        liquidity_delta = ticks_net_liquidity_mapping.get(tick, 0)
        current_liquidity += liquidity_delta

        bottom_tick = tick
        top_tick = bottom_tick + tick_spacing
        sqrt_price_current = tick_to_price(bottom_tick / 2)
        sqrt_price_next = tick_to_price(top_tick / 2)

        # Compute how much token0 we need to move to the next tick
        delta_y = current_liquidity * (sqrt_price_next - sqrt_price_current)
        delta_x = delta_y / (sqrt_price_next * sqrt_price_current)

        if amount_in_remaining >= delta_x:
            # If we have enough token0 to swap fully in this range
            total_token1_out += delta_y
            amount_in_remaining -= delta_x
        else:
            # If not, calculate partial swap based on remaining token0
            delta_y_partial = amount_in_remaining * sqrt_price_current * sqrt_price_next
            total_token1_out += delta_y_partial
            break  # Stop as we've used up all input

        tick += tick_spacing

    return int(total_token1_out)


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


def swap_quote_token1_to_token0_2(
    amount_in: int, ticks_net_liquidity_mapping: dict, pool_state: PoolState
) -> int:
    tick_spacing = TICK_SPACING

    current_tick = pool_state.current_tick
    current_liquidity = pool_state.current_liquidity

    min_tick = min(ticks_net_liquidity_mapping.keys())

    current_range_bottom_tick = math.floor(current_tick / tick_spacing) * tick_spacing
    amount_in_remaining = amount_in
    total_token0_out = 0
    tick = current_range_bottom_tick

    while amount_in_remaining > 0 and tick >= min_tick:
        liquidity_delta = ticks_net_liquidity_mapping.get(tick, 0)
        current_liquidity += liquidity_delta

        top_tick = tick
        bottom_tick = top_tick - tick_spacing
        sqrt_price_current = tick_to_price(top_tick / 2)
        sqrt_price_next = tick_to_price(bottom_tick / 2)

        # Compute how much token1 is required to move to the next tick
        delta_x = current_liquidity * (1 / sqrt_price_next - 1 / sqrt_price_current)
        delta_y = delta_x * sqrt_price_current * sqrt_price_next

        if amount_in_remaining >= delta_y:
            # If we have enough token1 to swap fully in this range
            total_token0_out += delta_x
            amount_in_remaining -= delta_y
        else:
            # If not, calculate partial swap based on remaining token1
            delta_x_partial = amount_in_remaining / (
                sqrt_price_current * sqrt_price_next
            )
            total_token0_out += delta_x_partial
            break  # Stop as we've used up all input

        tick -= tick_spacing

    return int(total_token0_out)


def tick_to_price(tick):
    return TICK_BASE**tick


@dataclass
class SwapCache:
    ## liquidity at the beginning of the swap
    liquidityStart: int


## the top level state of the swap, the results of which are recorded in storage at the end
@dataclass
class SwapState:
    ## the amount remaining to be swapped in#out of the input#output asset
    amountSpecifiedRemaining: int
    ## the amount already swapped out#in of the output#input asset
    amountCalculated: int
    ## current sqrt(price)
    sqrtPriceX96: int
    ## the tick associated with the current price
    tick: int
    ## the global fee growth of the input token
    feeGrowthGlobalX128: int
    ## the current liquidity in range
    liquidity: int


@dataclass
class StepComputations:
    ## the price at the beginning of the step
    sqrtPriceStartX96: int
    ## the next tick to swap to from the current tick in the swap direction
    tickNext: int
    ## whether tickNext is initialized or not
    initialized: bool
    ## sqrt(price) for the next tick (1#0)
    sqrtPriceNextX96: int
    ## how much is being swapped in in this step
    amountIn: int
    ## how much is being swapped out
    amountOut: int
    ## how much fee is being paid in
    feeAmount: int


@dataclass
class Slot0:
    ## the current price
    sqrtPriceX96: int
    ## the current tick
    tick: int


def nextTick(ticks, tick, lte):
    checkInputTypes(int24=(tick), bool=(lte))

    keyList = list(ticks)

    # If tick doesn't exist in the mapping we fake it (easier than searching for nearest value). This is probably not the
    # best way, but it is a simple and intuitive way to reproduce the behaviour of the logic.
    if not ticks.__contains__(tick):
        keyList += [tick]
    sortedKeyList = sorted(keyList)
    indexCurrentTick = sortedKeyList.index(tick)

    if lte:
        # If the current tick is initialized (not faked), we return the current tick
        if ticks.__contains__(tick):
            return tick, True
        elif indexCurrentTick == 0:
            # No tick to the left
            return TickMath.MIN_TICK, False
        else:
            nextTick = sortedKeyList[indexCurrentTick - 1]
    else:

        if indexCurrentTick == len(sortedKeyList) - 1:
            # No tick to the right
            return TickMath.MAX_TICK, False
        nextTick = sortedKeyList[indexCurrentTick + 1]

    # Return tick within the boundaries
    return nextTick, True


def swap_quote(
    ticks,
    slot0,
    liquidity,
    zero_for_one,
    amount_specified,
    sqrt_price_limit_x96,
):
    assert amount_specified != 0, "AS"

    if zero_for_one:
        assert (
            sqrt_price_limit_x96 < slot0.sqrtPriceX96
            and sqrt_price_limit_x96 > TickMath.MIN_SQRT_RATIO
        ), "SPL"
    else:
        assert (
            sqrt_price_limit_x96 > slot0.sqrtPriceX96
            and sqrt_price_limit_x96 < TickMath.MAX_SQRT_RATIO
        ), "SPL"

    cache = SwapCache(liquidity)

    exactInput = amount_specified > 0

    state = SwapState(
        amountSpecifiedRemaining=amount_specified,
        amountCalculated=0,
        sqrtPriceX96=slot0.sqrtPriceX96,
        tick=slot0.tick,
        feeGrowthGlobalX128=0,
        liquidity=cache.liquidityStart,
    )

    while (
        state.amountSpecifiedRemaining != 0
        and state.sqrtPriceX96 != sqrt_price_limit_x96
    ):
        step = StepComputations(0, 0, 0, 0, 0, 0, 0)
        step.sqrtPriceStartX96 = state.sqrtPriceX96

        (step.tickNext, step.initialized) = nextTick(ticks, state.tick, zero_for_one)

        ## get the price for the next tick
        step.sqrtPriceNextX96 = TickMath.getSqrtRatioAtTick(step.tickNext)

        ## compute values to swap to the target tick, price limit, or point where input#output amount is exhausted
        if zero_for_one:
            sqrtRatioTargetX96 = (
                sqrt_price_limit_x96
                if step.sqrtPriceNextX96 < sqrt_price_limit_x96
                else step.sqrtPriceNextX96
            )
        else:
            sqrtRatioTargetX96 = (
                sqrt_price_limit_x96
                if step.sqrtPriceNextX96 > sqrt_price_limit_x96
                else step.sqrtPriceNextX96
            )

        (
            state.sqrtPriceX96,
            step.amountIn,
            step.amountOut,
            step.feeAmount,
        ) = SwapMath.computeSwapStep(
            state.sqrtPriceX96,
            sqrtRatioTargetX96,
            state.liquidity,
            state.amountSpecifiedRemaining,
            10000,
        )
        if exactInput:
            state.amountSpecifiedRemaining -= step.amountIn + step.feeAmount
            state.amountCalculated = SafeMath.subInts(
                state.amountCalculated, step.amountOut
            )
        else:
            state.amountSpecifiedRemaining += step.amountOut
            state.amountCalculated = SafeMath.addInts(
                state.amountCalculated, step.amountIn + step.feeAmount
            )

        ## update global fee tracker
        if state.liquidity > 0:
            state.feeGrowthGlobalX128 += FullMath.mulDiv(
                step.feeAmount, FixedPoint128_Q128, state.liquidity
            )
            # Addition can overflow in Solidity - mimic it
            state.feeGrowthGlobalX128 = toUint256(state.feeGrowthGlobalX128)

        ## shift tick if we reached the next price
        if state.sqrtPriceX96 == step.sqrtPriceNextX96:
            ## if the tick is initialized, run the tick transition
            ## @dev: here is where we should handle the case of an uninitialized boundary tick
            if step.initialized:
                liquidityNet = LibTick.cross(
                    ticks,
                    step.tickNext,
                    0,
                    0,
                )
                ## if we're moving leftward, we interpret liquidityNet as the opposite sign
                ## safe because liquidityNet cannot be type(int128).min
                if zero_for_one:
                    liquidityNet = -liquidityNet

                state.liquidity = LiquidityMath.addDelta(state.liquidity, liquidityNet)

            state.tick = (step.tickNext - 1) if zero_for_one else step.tickNext
        elif state.sqrtPriceX96 != step.sqrtPriceStartX96:
            ## recompute unless we're on a lower tick boundary (i.e. already transitioned ticks), and haven't moved
            state.tick = TickMath.getTickAtSqrtRatio(state.sqrtPriceX96)

    (amount0, amount1) = (
        (amount_specified - state.amountSpecifiedRemaining, state.amountCalculated)
        if (zero_for_one == exactInput)
        else (
            state.amountCalculated,
            amount_specified - state.amountSpecifiedRemaining,
        )
    )

    return (
        amount0,
        amount1,
        state.sqrtPriceX96,
        state.liquidity,
        state.tick,
    )


if __name__ == "__main__":
    start_time = time.time()
    ticks = fetch_all_ticks("WETH-Bowling", POOL_ADDRESS)
    print(f"Fetched {len(ticks)} ticks")
    for tick in ticks:
        print(tick)
    tick_mapping = {tick.tick_index: tick for tick in ticks}
    end_time = time.time()
    print(f"Execution time: {end_time - start_time} seconds")

    token0 = pool_contract.functions.token0().call()
    token1 = pool_contract.functions.token1().call()
    print(f"Token0: {token0}, Token1: {token1}")
    decimals0 = 18
    decimals1 = 18
    print(f"Decimals0: {decimals0}, Decimals1: {decimals1}")

    start_time = time.time()
    slot0_start_resp = pool_contract.functions.slot0().call()
    slot0_start = Slot0(slot0_start_resp[0], slot0_start_resp[1])

    liquidity = pool_contract.functions.liquidity().call()
    end_time = time.time()
    print(f"Execution time: {end_time - start_time} seconds")
    print(f"Slot0: {slot0_start.sqrtPriceX96}, {slot0_start.tick}")
    print(f"Liquidity: {liquidity}")

    start_time = time.time()
    (
        amount0,
        amount1,
        sqrtPriceX96,
        liquidity,
        tick,
    ) = swap_quote(
        tick_mapping, slot0_start, liquidity, True, 5 * 10**17, MIN_SQRT_RATIO + 1
    )
    print(f"Amount0: {amount0/10**decimals0}, Amount1: {amount1/10**decimals1}")
    print(f"SqrtPriceX96: {sqrtPriceX96}, Liquidity: {liquidity}, Tick: {tick}")

    (
        amount0,
        amount1,
        sqrtPriceX96,
        liquidity,
        tick,
    ) = swap_quote(
        tick_mapping,
        slot0_start,
        liquidity,
        False,
        100000000 * 10**18,
        MAX_SQRT_RATIO - 1,
    )
    print(f"Amount0: {amount0/10**decimals0}, Amount1: {amount1/10**decimals1}")
    print(f"SqrtPriceX96: {sqrtPriceX96}, Liquidity: {liquidity}, Tick: {tick}")
    print(f"Execution time: {time.time() - start_time} seconds")
