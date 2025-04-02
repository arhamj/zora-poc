import time
from eth_typing import HexStr
from web3 import Web3
import json


# Configuration
RPC_URL = "http://base-proxy.lat.nodes.internal.notnotzora.com"
POOL_ADDRESS = Web3.to_checksum_address("0xE020E67Cb76C780329d4c205578Aaa6d6478Fb2A")
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

tick_liquidity_map = {}


def fetch_tick_liquidity(tick):
    try:
        result = pool_contract.functions.ticks(tick).call()
        liquidity_gross = result[0]
        tick_liquidity_map[tick] = liquidity_gross
        # print(f"Updated tick {tick} liquidity: {liquidity_gross}")
    except Exception as e:
        print(f"Error fetching liquidity for tick {tick}: {e}")


def handle_mint(log) -> None:
    event = pool_contract.events.Mint.process_log(log)
    tick_lower = event["args"]["tickLower"]
    tick_upper = event["args"]["tickUpper"]

    # print(f"[Mint] Refreshing liquidity for ticks {tick_lower} to {tick_upper}")
    fetch_tick_liquidity(tick_lower)
    fetch_tick_liquidity(tick_upper)


def handle_burn(log) -> None:
    event = pool_contract.events.Burn.process_log(log)
    tick_lower = event["args"]["tickLower"]
    tick_upper = event["args"]["tickUpper"]

    # print(f"[Burn] Refreshing liquidity for ticks {tick_lower} to {tick_upper}")
    fetch_tick_liquidity(tick_lower)
    fetch_tick_liquidity(tick_upper)


def handle_swap(log) -> None:
    event = pool_contract.events.Swap.process_log(log)
    tick = event["args"]["tick"]

    # print(f"[Swap] Swap event tx_hash: {event.transactionHash.hex()}")
    # print(f"[Swap] Detected at tick {tick}, fetching latest liquidity")
    fetch_tick_liquidity(tick)


handlers = {
    "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde": handle_mint,
    "0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c": handle_burn,
    "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67": handle_swap,
}


def process_block_range(from_block: int, to_block: int, topics: list[str]) -> None:
    hex_topics = [HexStr(t) for t in topics]
    logs = w3.eth.get_logs(
        {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": POOL_ADDRESS,
            "topics": [hex_topics],
        }
    )
    print(f"Fetched {len(logs)} logs from block {from_block} to {to_block}")
    for log in logs:
        handler = handlers.get(log["topics"][0].to_0x_hex())
        if handler:
            handler(log)
        else:
            print(f"Unknown event: {log['topics'][0].to_0x_hex()}")
            continue


def main() -> None:
    print("Listening for Mint, Burn, and Swap events...")
    fromBlock = 26316951
    batchSize = 100000
    while True:
        process_block_range(
            fromBlock,
            fromBlock + batchSize,
            [
                "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde",
                "0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c",
                "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67",
            ],
        )
        print(f"Liquidity map: {tick_liquidity_map}")
        fromBlock += batchSize
        if fromBlock > w3.eth.block_number:
            print(f"Reached latest block {w3.eth.block_number}, sleeping...")
            fromBlock = w3.eth.block_number
            time.sleep(5)
            print(f"Liquidity map: {tick_liquidity_map}")


if __name__ == "__main__":
    main()
