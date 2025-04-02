class PoolState:
    def __init__(self, current_tick: int, current_liquidity: int):
        self.current_tick = current_tick
        self.current_liquidity = current_liquidity

    def __repr__(self):
        return f"PoolState(current_tick={self.current_tick}, current_liquidity={self.current_liquidity})"


class Tick:
    def __init__(self, tick_index: int, liquidity_gross: int, liquidity_net: int):
        self.tick_index = tick_index
        self.liquidity_gross = liquidity_gross
        self.liquidity_net = liquidity_net

    def __repr__(self):
        return f"Tick(tick_index={self.tick_index}, liquidity_gross={self.liquidity_gross}, liquidity_net={self.liquidity_net})"
