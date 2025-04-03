from web3 import Web3
import json


# Configuration
RPC_URL = "http://base-proxy.lat.nodes.internal.notnotzora.com"
QUOTER_ADDRESS = Web3.to_checksum_address("0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a")
UNISWAP_V3_QUOTER_ABI_PATH = "src/zora_poc/UniswapV3Quoter.json"

# Web3 setup
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise Exception("Failed to connect to Ethereum node")

# Load Uniswap V3 Pool ABI
with open(UNISWAP_V3_QUOTER_ABI_PATH, "r") as abi_file:
    uniswap_v3_quoter_abi = json.load(abi_file)

# Contract setup
quoter_contract = w3.eth.contract(address=QUOTER_ADDRESS, abi=uniswap_v3_quoter_abi)

token0 = "0x4200000000000000000000000000000000000006"
token1 = "0x72C6b9d34c15bfc270Db206BCF9B5417dEbD955F"
fee = 3000
amount_in = 100000000000000000


def fetch_quote() -> None:
    amount_out = quoter_contract.functions.quoteExactInputSingle(
        w3.to_checksum_address(token0),
        w3.to_checksum_address(token1),
        fee,
        amount_in,
        0,
    ).call()
    print(f"Amount out: {amount_out}")


if __name__ == "__main__":
    fetch_quote()
