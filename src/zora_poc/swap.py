from typing import Dict, Tuple


class TickBitmap:
    # Reference: https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/TickBitmap.sol

    def __init__(self, position_mapping):
        self.position_mapping = position_mapping

    def next_initialized_tick_within_one_word(self, tick, tick_spacing, zero_for_one):
        """
        Returns the next initialized tick contained in the same word as the current tick

        Args:
            tick: The current tick
            tick_spacing: The spacing between usable ticks
            zero_for_one: Direction of swap

        Returns:
            tuple: (next_tick, initialized) - the next tick and whether it's initialized
        """
        # Compute the compressed tick
        compressed = self._get_compressed_tick(tick, tick_spacing)

        # Compute the position and shift amount
        word_pos, bit_pos = self._position(compressed)

        # Get the appropriate mask depending on the direction
        if zero_for_one:
            # Search from right to left, starting at bit_pos
            mask = (1 << bit_pos) - 1 + (1 << bit_pos)
        else:
            # Search from left to right, starting after bit_pos
            mask = ~((1 << bit_pos) - 1) if bit_pos != 0 else 2**256 - 1

        # Apply the mask to get the relevant bits
        masked_word = self.position_mapping.get(word_pos, 0) & mask

        # If no initialized tick is found in the current word
        if masked_word == 0:
            # Go to the next word
            next_word_pos = word_pos - 1 if zero_for_one else word_pos + 1
            # If the next word is empty
            if (
                next_word_pos not in self.position_mapping
                or self.position_mapping[next_word_pos] == 0
            ):
                # Return the next multiple of 256 * tick_spacing
                return (
                    (
                        self._min_tick_in_word(next_word_pos, tick_spacing)
                        if zero_for_one
                        else self._max_tick_in_word(next_word_pos, tick_spacing)
                    ),
                    False,
                )
            # Get the first initialized bit in the next word
            next_bit = (
                self._most_significant_bit(self.position_mapping[next_word_pos])
                if zero_for_one
                else self._least_significant_bit(self.position_mapping[next_word_pos])
            )
        else:
            # Get the next initialized bit in the current word
            next_bit = (
                self._most_significant_bit(masked_word)
                if zero_for_one
                else self._least_significant_bit(masked_word)
            )
            next_word_pos = word_pos

        # Calculate the next initialized tick
        next_initialized_tick = self._get_decompressed_tick(
            (next_word_pos << 8) + next_bit, tick_spacing
        )

        return (next_initialized_tick, True)

    def _get_compressed_tick(self, tick, tick_spacing):
        """Compress tick to mapping space"""
        return tick // tick_spacing

    def _get_decompressed_tick(self, compressed_tick, tick_spacing):
        """Decompress tick from mapping space"""
        return compressed_tick * tick_spacing

    def _position(self, tick):
        """
        Calculate the word and bit position for a tick

        Returns:
            tuple: (word_pos, bit_pos)
        """
        word_pos = tick >> 8
        bit_pos = tick & 0xFF
        return (word_pos, bit_pos)

    def _min_tick_in_word(self, word_pos, tick_spacing):
        """Find the minimum tick in a word"""
        return self._get_decompressed_tick(word_pos << 8, tick_spacing)

    def _max_tick_in_word(self, word_pos, tick_spacing):
        """Find the maximum tick in a word"""
        return self._get_decompressed_tick((word_pos << 8) + 255, tick_spacing)

    def _most_significant_bit(self, x):
        """Find the position of the most significant bit"""
        return x.bit_length() - 1

    def _least_significant_bit(self, x):
        """Find the position of the least significant bit"""
        return (x & -x).bit_length() - 1


class TickMath:
    # Reference: https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/TickMath.sol

    # Tick range constants
    MIN_TICK = -887272
    MAX_TICK = 887272

    # Price range constants

    MIN_SQRT_RATIO = 4295128739
    MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342

    def get_sqrt_ratio_at_tick(self, tick):
        """
        Calculates sqrt(1.0001^tick) * 2^96

        Args:
            tick: The tick for which to compute the square root ratio

        Returns:
            int: The square root ratio in Q64.96 format
        """
        # Validate input
        assert tick >= self.MIN_TICK and tick <= self.MAX_TICK, "T"

        abs_tick = abs(tick)

        # Precomputed values for powers of 1.0001
        sqrt_ratios = {
            0: 1 << 96,  # 1.0 in Q64.96
            1: 1000050000000000000000000,  # sqrt(1.0001) in Q64.96
            2: 1000100002500000000000000,  # sqrt(1.0001^2) in Q64.96
            4: 1000200010000000000000000,
            8: 1000400060004000000000000,
            16: 1000800240019200000000000,
            32: 1001601920152454400000000,
            64: 1003210079306990600000000,
            128: 1006446002925730300000000,
            256: 1012968394718193900000000,
            512: 1026258773870968500000000,
            1024: 1053183768888205700000000,
            2048: 1109785300683885200000000,
            4096: 1232056666469055300000000,
            8192: 1518386105058158600000000,
            16384: 2305485905613683200000000,
            32768: 5316911983139663500000000,
            65536: 28245488103320099000000000,
            131072: 797537631168331300000000000,
            262144: 636562399226427700000000000000,
            524288: 405211456133234100000000000000000,
        }

        # Initialize ratio
        ratio = 1 << 96

        # Compute using powers of 2
        if abs_tick & 0x1 != 0:
            ratio = (ratio * sqrt_ratios[1]) // (1 << 96)
        if abs_tick & 0x2 != 0:
            ratio = (ratio * sqrt_ratios[2]) // (1 << 96)
        if abs_tick & 0x4 != 0:
            ratio = (ratio * sqrt_ratios[4]) // (1 << 96)
        if abs_tick & 0x8 != 0:
            ratio = (ratio * sqrt_ratios[8]) // (1 << 96)
        if abs_tick & 0x10 != 0:
            ratio = (ratio * sqrt_ratios[16]) // (1 << 96)
        if abs_tick & 0x20 != 0:
            ratio = (ratio * sqrt_ratios[32]) // (1 << 96)
        if abs_tick & 0x40 != 0:
            ratio = (ratio * sqrt_ratios[64]) // (1 << 96)
        if abs_tick & 0x80 != 0:
            ratio = (ratio * sqrt_ratios[128]) // (1 << 96)
        if abs_tick & 0x100 != 0:
            ratio = (ratio * sqrt_ratios[256]) // (1 << 96)
        if abs_tick & 0x200 != 0:
            ratio = (ratio * sqrt_ratios[512]) // (1 << 96)
        if abs_tick & 0x400 != 0:
            ratio = (ratio * sqrt_ratios[1024]) // (1 << 96)
        if abs_tick & 0x800 != 0:
            ratio = (ratio * sqrt_ratios[2048]) // (1 << 96)
        if abs_tick & 0x1000 != 0:
            ratio = (ratio * sqrt_ratios[4096]) // (1 << 96)
        if abs_tick & 0x2000 != 0:
            ratio = (ratio * sqrt_ratios[8192]) // (1 << 96)
        if abs_tick & 0x4000 != 0:
            ratio = (ratio * sqrt_ratios[16384]) // (1 << 96)
        if abs_tick & 0x8000 != 0:
            ratio = (ratio * sqrt_ratios[32768]) // (1 << 96)
        if abs_tick & 0x10000 != 0:
            ratio = (ratio * sqrt_ratios[65536]) // (1 << 96)
        if abs_tick & 0x20000 != 0:
            ratio = (ratio * sqrt_ratios[131072]) // (1 << 96)
        if abs_tick & 0x40000 != 0:
            ratio = (ratio * sqrt_ratios[262144]) // (1 << 96)
        if abs_tick & 0x80000 != 0:
            ratio = (ratio * sqrt_ratios[524288]) // (1 << 96)

        # If tick is negative, invert the ratio
        if tick < 0:
            ratio = (1 << 192) // ratio

        return ratio

    def get_tick_at_sqrt_ratio(self, sqrt_ratio_x96):
        """
        Calculates the largest tick such that getRatioAtTick(tick) <= ratio

        Args:
            sqrt_ratio_x96: The sqrt ratio for which to compute the tick

        Returns:
            int: The greatest tick whose sqrt ratio is <= sqrt_ratio_x96
        """
        # Validate input
        assert (
            sqrt_ratio_x96 >= self.MIN_SQRT_RATIO
            and sqrt_ratio_x96 <= self.MAX_SQRT_RATIO
        ), "R"

        # Use binary search to find the tick
        lower_tick = self.MIN_TICK
        upper_tick = self.MAX_TICK

        while upper_tick - lower_tick > 1:
            mid_tick = (lower_tick + upper_tick) // 2
            mid_ratio = self.get_sqrt_ratio_at_tick(mid_tick)

            if mid_ratio <= sqrt_ratio_x96:
                lower_tick = mid_tick
            else:
                upper_tick = mid_tick

        # Return the greatest tick value that's less than or equal to the target ratio
        if self.get_sqrt_ratio_at_tick(upper_tick) <= sqrt_ratio_x96:
            return upper_tick
        else:
            return lower_tick


class SwapMath:
    # Reference: https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/SwapMath.sol
    def compute_swap_step(
        self,
        sqrt_ratio_current_x96,
        sqrt_ratio_target_x96,
        liquidity,
        amount_remaining,
        fee_pips,
    ):
        """
        Computes a single step of a swap

        Args:
            sqrt_ratio_current_x96: The current sqrt price
            sqrt_ratio_target_x96: The target sqrt price
            liquidity: The available liquidity
            amount_remaining: The remaining amount to swap (can be negative)
            fee_pips: The fee in hundredths of a bip (1/1000000)

        Returns:
            tuple: (sqrt_ratio_next_x96, amount_in, amount_out, fee_amount)
        """
        # Create reference to FullMath for calculations
        full_math = FullMath()

        # Set swap direction
        zero_for_one = sqrt_ratio_current_x96 >= sqrt_ratio_target_x96
        exact_in = amount_remaining >= 0

        # Calculate sqrt price delta
        if exact_in:
            # Calculate the max input amount considering the fee
            amount_remaining_less_fee = (
                amount_remaining * (1_000_000 - fee_pips)
            ) // 1_000_000

            if zero_for_one:
                # Calculate max amount that can be swapped from token0 to token1
                amount_in = self._compute_amount0_delta(
                    sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity, True
                )
            else:
                # Calculate max amount that can be swapped from token1 to token0
                amount_in = self._compute_amount1_delta(
                    sqrt_ratio_current_x96, sqrt_ratio_target_x96, liquidity, True
                )

            # Determine sqrt_ratio_next based on the input amount
            if amount_remaining_less_fee >= amount_in:
                sqrt_ratio_next_x96 = sqrt_ratio_target_x96
            else:
                sqrt_ratio_next_x96 = self._get_next_sqrt_price_from_input(
                    sqrt_ratio_current_x96,
                    liquidity,
                    amount_remaining_less_fee,
                    zero_for_one,
                )
        else:
            if zero_for_one:
                # Calculate max amount that can be received from token0 to token1
                amount_out = self._compute_amount1_delta(
                    sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity, False
                )
            else:
                # Calculate max amount that can be received from token1 to token0
                amount_out = self._compute_amount0_delta(
                    sqrt_ratio_current_x96, sqrt_ratio_target_x96, liquidity, False
                )

            # Determine sqrt_ratio_next based on the output amount
            if abs(amount_remaining) >= amount_out:
                sqrt_ratio_next_x96 = sqrt_ratio_target_x96
            else:
                sqrt_ratio_next_x96 = self._get_next_sqrt_price_from_output(
                    sqrt_ratio_current_x96,
                    liquidity,
                    abs(amount_remaining),
                    zero_for_one,
                )

        # Calculate max(0, sqrt_ratio_target - sqrt_ratio_current)
        max_price = max(sqrt_ratio_target_x96, sqrt_ratio_current_x96)
        min_price = min(sqrt_ratio_target_x96, sqrt_ratio_current_x96)

        # Compute input and output amounts
        if zero_for_one:
            amount_in = (
                0
                if sqrt_ratio_next_x96 >= sqrt_ratio_current_x96
                else self._compute_amount0_delta(
                    sqrt_ratio_next_x96, sqrt_ratio_current_x96, liquidity, True
                )
            )
            amount_out = (
                0
                if sqrt_ratio_next_x96 >= sqrt_ratio_current_x96
                else self._compute_amount1_delta(
                    sqrt_ratio_next_x96, sqrt_ratio_current_x96, liquidity, False
                )
            )
        else:
            amount_in = (
                0
                if sqrt_ratio_next_x96 <= sqrt_ratio_current_x96
                else self._compute_amount1_delta(
                    sqrt_ratio_current_x96, sqrt_ratio_next_x96, liquidity, True
                )
            )
            amount_out = (
                0
                if sqrt_ratio_next_x96 <= sqrt_ratio_current_x96
                else self._compute_amount0_delta(
                    sqrt_ratio_current_x96, sqrt_ratio_next_x96, liquidity, False
                )
            )

        # Calculate fee amount
        if exact_in and amount_in > 0:
            # Calculate fee from: (amount_in_with_fee - amount_in)
            fee_amount = full_math.mul_div_round_up(
                amount_in, fee_pips, 1_000_000 - fee_pips
            )
        else:
            fee_amount = 0

        return (sqrt_ratio_next_x96, amount_in, amount_out, fee_amount)

    def _compute_amount0_delta(
        self, sqrt_ratio_a_x96, sqrt_ratio_b_x96, liquidity, round_up
    ):
        """
        Computes the token0 delta given price change and liquidity

        Args:
            sqrt_ratio_a_x96: First sqrt price
            sqrt_ratio_b_x96: Second sqrt price
            liquidity: The liquidity amount
            round_up: Whether to round up or down

        Returns:
            int: The amount of token0
        """
        # Ensure sqrt_ratio_a <= sqrt_ratio_b for simplicity
        if sqrt_ratio_a_x96 > sqrt_ratio_b_x96:
            sqrt_ratio_a_x96, sqrt_ratio_b_x96 = sqrt_ratio_b_x96, sqrt_ratio_a_x96

        # Calculate amount:
        # L * (pb - pa) / (pa * pb)
        numerator1 = liquidity << 96
        numerator2 = sqrt_ratio_b_x96 - sqrt_ratio_a_x96
        full_math = FullMath()

        if round_up:
            # For exact output case, round up
            return (
                full_math.mul_div_round_up(numerator1, numerator2, sqrt_ratio_b_x96)
                // sqrt_ratio_a_x96
            )
        else:
            # For exact input case, round down
            return (
                full_math.mul_div(numerator1, numerator2, sqrt_ratio_b_x96)
                // sqrt_ratio_a_x96
            )

    def _compute_amount1_delta(
        self, sqrt_ratio_a_x96, sqrt_ratio_b_x96, liquidity, round_up
    ):
        """
        Computes the token1 delta given price change and liquidity

        Args:
            sqrt_ratio_a_x96: First sqrt price
            sqrt_ratio_b_x96: Second sqrt price
            liquidity: The liquidity amount
            round_up: Whether to round up or down

        Returns:
            int: The amount of token1
        """
        # Ensure sqrt_ratio_a <= sqrt_ratio_b for simplicity
        if sqrt_ratio_a_x96 > sqrt_ratio_b_x96:
            sqrt_ratio_a_x96, sqrt_ratio_b_x96 = sqrt_ratio_b_x96, sqrt_ratio_a_x96

        # Calculate amount:
        # L * (pb - pa)
        full_math = FullMath()

        if round_up:
            # For exact output case, round up
            return full_math.mul_div_round_up(
                liquidity, sqrt_ratio_b_x96 - sqrt_ratio_a_x96, 1 << 96
            )
        else:
            # For exact input case, round down
            return full_math.mul_div(
                liquidity, sqrt_ratio_b_x96 - sqrt_ratio_a_x96, 1 << 96
            )

    def _get_next_sqrt_price_from_input(
        self, sqrt_price_x96, liquidity, amount_in, zero_for_one
    ):
        """
        Compute the next sqrt price after swapping some amount in

        Args:
            sqrt_price_x96: The current sqrt price
            liquidity: The current liquidity
            amount_in: The input amount
            zero_for_one: Whether token0 or token1 is being swapped in

        Returns:
            int: The next sqrt price
        """
        assert amount_in > 0
        assert liquidity > 0
        full_math = FullMath()

        if zero_for_one:
            # Token0 is being swapped in
            # Formula: price - amount * price / ((price * liquidity)/(2^96) + amount)
            numerator = liquidity << 96
            product = amount_in * sqrt_price_x96
            denominator = numerator + product

            return full_math.mul_div(numerator, sqrt_price_x96, denominator)
        else:
            # Token1 is being swapped in
            # Formula: price + amount / liquidity
            quotient = full_math.mul_div(amount_in, 1 << 96, liquidity)

            return sqrt_price_x96 + quotient

    def _get_next_sqrt_price_from_output(
        self, sqrt_price_x96, liquidity, amount_out, zero_for_one
    ):
        """
        Compute the next sqrt price after swapping some amount out

        Args:
            sqrt_price_x96: The current sqrt price
            liquidity: The current liquidity
            amount_out: The output amount
            zero_for_one: Whether token0 or token1 is being swapped out

        Returns:
            int: The next sqrt price
        """
        assert amount_out > 0
        assert liquidity > 0
        full_math = FullMath()

        if zero_for_one:
            # Token1 is being swapped out
            # Formula: price - amount * 2^96 / liquidity
            quotient = full_math.mul_div_round_up(amount_out, 1 << 96, liquidity)

            # Ensure quotient isn't greater than sqrt_price_x96
            assert quotient < sqrt_price_x96

            return sqrt_price_x96 - quotient
        else:
            # Token0 is being swapped out
            # Formula: liquidity * price / (liquidity - amount * price / 2^96)
            numerator = liquidity << 96
            product = full_math.mul_div_round_up(amount_out, sqrt_price_x96, 1)

            # Ensure liquidity is greater than product
            assert numerator > product

            denominator = numerator - product

            return full_math.mul_div_round_up(numerator, sqrt_price_x96, denominator)


class LiquidityMath:
    def add_delta(self, x, y):
        """
        Add a signed liquidity delta to liquidity

        Args:
            x: Current liquidity value
            y: Liquidity delta to add

        Returns:
            int: The new liquidity value
        """
        if y < 0:
            # Handle decrease in liquidity
            assert x >= (-y), "LS"  # Liquidity Subtraction underflow
            z = x + y
        else:
            # Handle increase in liquidity
            z = x + y
            # Check for overflow
            assert z >= x, "LA"  # Liquidity Addition overflow

        return z


class FullMath:
    def mul_div(self, a, b, denominator):
        """
        Calculates floor(a×b÷denominator) with full precision

        Args:
            a: First multiplicand
            b: Second multiplicand
            denominator: Divisor

        Returns:
            int: The result of the calculation
        """
        assert denominator > 0

        if a == 0 or b == 0:
            return 0

        # Get the result using built-in operations
        result = (a * b) // denominator

        return result

    def mul_div_round_up(self, a, b, denominator):
        """
        Calculates ceil(a×b÷denominator) with full precision

        Args:
            a: First multiplicand
            b: Second multiplicand
            denominator: Divisor

        Returns:
            int: The result of the calculation, rounded up
        """
        assert denominator > 0

        if a == 0 or b == 0:
            return 0

        # Get the raw result
        result = (a * b) // denominator

        # Check if we need to round up
        if (a * b) % denominator > 0:
            result += 1

        return result


class Observations:
    # NOTE: This class is optional for us
    # It is to create the oracle for the pool

    def __init__(self, observations):
        """
        Initialize the oracle with observations

        Args:
            observations: List of observation records
        """
        self.observations = observations

    def observe_single(
        self,
        seconds_ago,
        current_time,
        current_tick,
        observation_index,
        current_liquidity,
        cardinality,
    ):
        """
        Returns the cumulative tick and liquidity values observed at secondsAgo seconds ago

        Args:
            seconds_ago: The number of seconds in the past to look back
            current_time: The current block timestamp
            current_tick: The current tick
            observation_index: The index of the latest observation
            current_liquidity: The current in-range pool liquidity
            cardinality: How many observations are currently stored

        Returns:
            tuple: (tick_cumulative, seconds_per_liquidity_cumulative_x128)
        """
        if seconds_ago == 0:
            # Return the current values
            observation = self.observations[observation_index]

            return (
                observation.tick_cumulative
                + (current_tick * (current_time - observation.block_timestamp)),
                observation.seconds_per_liquidity_cumulative_X128
                + self._get_seconds_per_liquidity_inside(
                    current_time - observation.block_timestamp, current_liquidity
                ),
            )

        # Find the observation from secondsAgo in the past
        target_time = current_time - seconds_ago
        oldest_index = (observation_index + 1) % cardinality
        oldest_observation = self.observations[oldest_index]

        # Make sure we're not looking beyond our oldest observation
        assert oldest_observation.block_timestamp <= target_time, "OLD"

        # Find the surrounding observations
        current_observation = self.observations[observation_index]
        before_or_at = None
        after_or_at = None

        # Handle the case where the target is exactly the current observation
        if current_observation.block_timestamp <= target_time:
            before_or_at = current_observation
            after_or_at = None  # No after observation
        else:
            # Binary search through the observations to find surrounding points
            upper_index = observation_index
            lower_index = (observation_index + 1) % cardinality

            # Continue search until we find observations surrounding the target time
            while True:
                # Midpoint of the binary search
                mid_index = (lower_index + upper_index) // 2

                # Check if we've narrowed down to consecutive observations
                if lower_index == mid_index:
                    break

                mid_observation = self.observations[mid_index]

                if mid_observation.block_timestamp <= target_time:
                    lower_index = mid_index
                else:
                    upper_index = mid_index

            # Set before and after observations
            before_or_at = self.observations[lower_index]
            after_or_at = self.observations[upper_index]

        # When we have surrounding observations, interpolate between them
        if before_or_at is not None and after_or_at is not None:
            # Linear interpolation formula
            time_delta = after_or_at.block_timestamp - before_or_at.block_timestamp
            time_point_delta = target_time - before_or_at.block_timestamp

            tick_cumulative = (
                before_or_at.tick_cumulative
                + (after_or_at.tick_cumulative - before_or_at.tick_cumulative)
                * time_point_delta
                // time_delta
            )

            seconds_per_liquidity_cumulative = (
                before_or_at.seconds_per_liquidity_cumulative_X128
                + (
                    after_or_at.seconds_per_liquidity_cumulative_X128
                    - before_or_at.seconds_per_liquidity_cumulative_X128
                )
                * time_point_delta
                // time_delta
            )

            return (tick_cumulative, seconds_per_liquidity_cumulative)

        # If we only have the beforeOrAt observation
        if before_or_at is not None:
            return (
                before_or_at.tick_cumulative,
                before_or_at.seconds_per_liquidity_cumulative_X128,
            )

        # If we only have the afterOrAt observation (should not happen with valid input)
        return (
            after_or_at.tick_cumulative,
            after_or_at.seconds_per_liquidity_cumulative_X128,
        )

    def write(
        self, index, block_timestamp, tick, liquidity, cardinality, cardinality_next
    ):
        """
        Writes an oracle observation

        Args:
            index: The index of the observation to update
            block_timestamp: The timestamp of the current block
            tick: The active tick at the time of the observation
            liquidity: The total in-range liquidity at the time of the observation
            cardinality: The number of populated elements in the oracle array
            cardinality_next: The new length of the oracle array

        Returns:
            tuple: (index, cardinality) - the next index and cardinality values
        """
        current_observation = self.observations[index]

        # Don't overwrite an observation that's already been written
        if current_observation.block_timestamp == block_timestamp:
            return (index, cardinality)

        # If we're initializing the oracle, populate the first slot
        if cardinality > 0:
            # Get the previous observation
            prev_index = (index + cardinality - 1) % cardinality
            prev_observation = self.observations[prev_index]

            # Calculate time and tick changes since the last observation
            time_delta = block_timestamp - prev_observation.block_timestamp
            tick_cumulative = prev_observation.tick_cumulative + tick * time_delta
            seconds_per_liquidity_cumulative = (
                prev_observation.seconds_per_liquidity_cumulative_X128
                + self._get_seconds_per_liquidity_inside(time_delta, liquidity)
            )
        else:
            # First ever observation
            tick_cumulative = 0
            seconds_per_liquidity_cumulative = 0

        # Update the observation at the current index
        self.observations[index] = {
            "block_timestamp": block_timestamp,
            "tick_cumulative": tick_cumulative,
            "seconds_per_liquidity_cumulative_X128": seconds_per_liquidity_cumulative,
        }

        # Update index to the next slot
        next_index = (index + 1) % cardinality_next

        # If we need to update cardinality
        if next_index == 0:
            next_cardinality = cardinality_next
        else:
            next_cardinality = cardinality

        # If we've reached the full cardinality
        if cardinality < cardinality_next and next_index == 0:
            next_cardinality = cardinality + 1

        return (next_index, next_cardinality)

    def _get_seconds_per_liquidity_inside(self, seconds_delta, liquidity):
        """
        Calculate seconds per liquidity for a time period

        Args:
            seconds_delta: The time period in seconds
            liquidity: The liquidity amount

        Returns:
            int: seconds * Q128 / liquidity value
        """
        if liquidity <= 0:
            return 0

        return (seconds_delta << 128) // liquidity


class Ticks:
    # Referece: https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/Tick.sol

    def __init__(self, ticks):
        """
        Initialize the ticks mapping

        Args:
            ticks: Dictionary mapping tick indices to tick state
        """
        self.ticks = ticks

    def cross(
        self,
        tick,
        fee_growth_global0_x128,
        fee_growth_global1_x128,
        seconds_per_liquidity_cumulative_x128,
        tick_cumulative,
        time,
    ):
        """
        Executes the logic for crossing a tick

        Args:
            tick: The tick to cross
            fee_growth_global0_x128: The global fee growth of token0
            fee_growth_global1_x128: The global fee growth of token1
            seconds_per_liquidity_cumulative_x128: The seconds per liquidity value at crossing
            tick_cumulative: The cumulative tick value at crossing
            time: The current block timestamp

        Returns:
            int: The tick's liquidity net value
        """
        # Get the tick info
        info = self.ticks.get(
            tick,
            {
                "liquidity_gross": 0,
                "liquidity_net": 0,
                "fee_growth_outside0_x128": 0,
                "fee_growth_outside1_x128": 0,
                "tick_cumulative_outside": 0,
                "seconds_per_liquidity_outside_x128": 0,
                "seconds_outside": 0,
                "initialized": False,
            },
        )

        # If the tick isn't initialized, return 0 liquidity net
        if not info["initialized"]:
            return 0

        # Update the tick's fee growth outside values
        info["fee_growth_outside0_x128"] = (
            fee_growth_global0_x128 - info["fee_growth_outside0_x128"]
        )
        info["fee_growth_outside1_x128"] = (
            fee_growth_global1_x128 - info["fee_growth_outside1_x128"]
        )

        # Update the tick's seconds per liquidity and time tracking
        info["seconds_per_liquidity_outside_x128"] = (
            seconds_per_liquidity_cumulative_x128
            - info["seconds_per_liquidity_outside_x128"]
        )
        info["tick_cumulative_outside"] = (
            tick_cumulative - info["tick_cumulative_outside"]
        )
        info["seconds_outside"] = time - info["seconds_outside"]

        # Store the updated tick
        self.ticks[tick] = info

        return info["liquidity_net"]


class TransferHelper:
    def __init__(self, tokens):
        """
        Initialize with token balances

        Args:
            tokens: Dictionary mapping token addresses to account balances
        """
        self.tokens = tokens

    def safe_transfer(self, token, to, amount):
        """
        Execute a token transfer

        Args:
            token: Token address
            to: Recipient address
            amount: Amount to transfer
        """
        # Ensure the token exists
        if token not in self.tokens:
            self.tokens[token] = {}

        # Ensure the sender has a balance
        if "pool" not in self.tokens[token]:
            self.tokens[token]["pool"] = 0

        # Ensure the recipient has a balance
        if to not in self.tokens[token]:
            self.tokens[token][to] = 0

        # Check if the pool has enough balance
        assert self.tokens[token]["pool"] >= amount, "Insufficient balance"

        # Execute the transfer
        self.tokens[token]["pool"] -= amount
        self.tokens[token][to] += amount


class UniswapV3Pool:
    # Price range constants
    MIN_SQRT_RATIO = 4295128739
    MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342

    # Tick range constants
    MIN_TICK = -887272
    MAX_TICK = 887272

    # Precision constants
    Q96 = 2**96
    Q128 = 2**128

    def __init__(self, token0, token1, fee, tick_spacing):
        """
        Initialize a Uniswap V3 Pool

        Args:
            token0: Address of the first token
            token1: Address of the second token
            fee: Fee tier in hundredths of a bip (1/1000000)
            tick_spacing: Spacing between ticks
        """
        # Token addresses
        self.token0 = token0
        self.token1 = token1

        # Pool parameters
        self.fee = fee
        self.tick_spacing = tick_spacing

        # Pool state
        self.liquidity = 0
        self.fee_growth_global0_x128 = 0
        self.fee_growth_global1_x128 = 0
        self.protocol_fees = {"token0": 0, "token1": 0}

        # Slot0 state
        self.slot0 = {
            "sqrt_price_x96": 0,
            "tick": 0,
            "observation_index": 0,
            "observation_cardinality": 0,
            "observation_cardinality_next": 0,
            "fee_protocol": 0,
            "unlocked": True,
        }

        # Initialize helper classes
        self.tick_bitmap = TickBitmap({})
        self.ticks = Ticks({})
        self.tick_math = TickMath()
        self.swap_math = SwapMath()
        self.liquidity_math = LiquidityMath()
        self.full_math = FullMath()
        self.observations = Observations([])
        self.transfer_helper = TransferHelper({})

        # These would be initialized with actual implementations
        self.callback_handler = None

        # Token balances
        self._token_balances = {token0: 0, token1: 0}

    def initialize(self, sqrt_price_x96):
        """
        Initialize the pool with a starting price

        Args:
            sqrt_price_x96: Initial sqrt price in Q64.96 format
        """
        assert self.slot0["sqrt_price_x96"] == 0, "AI"  # Already initialized
        assert (
            sqrt_price_x96 >= self.MIN_SQRT_RATIO
            and sqrt_price_x96 <= self.MAX_SQRT_RATIO
        ), "R"  # Price bounds

        # Set initial price and tick
        tick = self.tick_math.get_tick_at_sqrt_ratio(sqrt_price_x96)

        # Initialize slot0
        self.slot0["sqrt_price_x96"] = sqrt_price_x96
        self.slot0["tick"] = tick

        # Initialize oracle
        self.slot0["observation_index"] = 0
        self.slot0["observation_cardinality"] = 1
        self.slot0["observation_cardinality_next"] = 1

        # Create first observation
        self.observations = Observations(
            [
                {
                    "block_timestamp": self._block_timestamp(),
                    "tick_cumulative": 0,
                    "seconds_per_liquidity_cumulative_X128": 0,
                }
            ]
        )

    def set_slot0(
        self,
        sqrt_price_x96,
        tick,
        observation_index,
        observation_cardinality,
        observation_cardinality_next,
        fee_protocol,
        unlocked=True,
    ):
        """
        Set the slot0 values directly - useful for testing or initializing from real data

        Args:
            sqrt_price_x96: Current sqrt price in Q64.96 format
            tick: Current tick
            observation_index: Current observation index
            observation_cardinality: Current oracle cardinality
            observation_cardinality_next: Next oracle cardinality
            fee_protocol: Protocol fee setting
            unlocked: Whether the pool is currently unlocked
        """
        self.slot0 = {
            "sqrt_price_x96": sqrt_price_x96,
            "tick": tick,
            "observation_index": observation_index,
            "observation_cardinality": observation_cardinality,
            "observation_cardinality_next": observation_cardinality_next,
            "fee_protocol": fee_protocol,
            "unlocked": unlocked,
        }

    def set_liquidity(self, liquidity):
        """Set the current pool liquidity"""
        self.liquidity = liquidity

    def set_fee_growth_globals(self, fee_growth_global0_x128, fee_growth_global1_x128):
        """Set fee growth global accumulators"""
        self.fee_growth_global0_x128 = fee_growth_global0_x128
        self.fee_growth_global1_x128 = fee_growth_global1_x128

    def set_protocol_fees(self, token0_fees, token1_fees):
        """Set accumulated protocol fees"""
        self.protocol_fees = {"token0": token0_fees, "token1": token1_fees}

    def set_tick_data(self, tick_bitmap_data, ticks_data):
        """
        Set tick bitmap and ticks data

        Args:
            tick_bitmap_data: Dictionary mapping word positions to bitmaps
            ticks_data: Dictionary mapping tick indices to tick states
        """
        self.tick_bitmap = TickBitmap(tick_bitmap_data)
        self.ticks = Ticks(ticks_data)

    def set_observations(self, observations_data):
        """Set oracle observations"""
        self.observations = Observations(observations_data)

    def set_token_balances(self, token0_balance, token1_balance):
        """Set token balances for the pool"""
        self._token_balances = {
            self.token0: token0_balance,
            self.token1: token1_balance,
        }

    def set_callback_handler(self, callback_handler):
        """Set the callback handler"""
        self.callback_handler = callback_handler

    def balance0(self):
        """Get token0 balance of the pool"""
        return self._token_balances[self.token0]

    def balance1(self):
        """Get token1 balance of the pool"""
        return self._token_balances[self.token1]

    def swap(
        self, recipient, zero_for_one, amount_specified, sqrt_price_limit_x96, data
    ):
        """
        Swap tokens in the pool.

        Args:
            recipient: Address that will receive the output tokens
            zero_for_one: Direction of swap (token0 to token1 if True)
            amount_specified: Amount to swap (positive = exact input, negative = exact output)
            sqrt_price_limit_x96: Price limit for the swap in Q64.96 format
            data: Data to be passed to the callback

        Returns:
            tuple: (amount0, amount1) representing token deltas
        """
        assert amount_specified != 0, "AS"  # Amount Specified must be non-zero

        # Cache the current state to avoid multiple storage reads
        slot0_start = self.slot0.copy()

        # Verify swap parameters are valid
        assert slot0_start["unlocked"], "LOK"  # Reentrancy lock

        if zero_for_one:
            assert (
                sqrt_price_limit_x96 < slot0_start["sqrt_price_x96"]
                and sqrt_price_limit_x96 > self.MIN_SQRT_RATIO
            ), "SPL"
        else:
            assert (
                sqrt_price_limit_x96 > slot0_start["sqrt_price_x96"]
                and sqrt_price_limit_x96 < self.MAX_SQRT_RATIO
            ), "SPL"

        # Lock the pool during the swap
        self.slot0["unlocked"] = False

        # Cache frequently accessed values
        cache = {
            "liquidity_start": self.liquidity,
            "block_timestamp": self._block_timestamp(),
            "fee_protocol": (
                slot0_start["fee_protocol"] % 16
                if zero_for_one
                else slot0_start["fee_protocol"] >> 4
            ),
            "seconds_per_liquidity_cumulative_x128": 0,
            "tick_cumulative": 0,
            "computed_latest_observation": False,
        }

        # Determine if this is an exact input or exact output swap
        exact_input = amount_specified > 0

        # Initialize the swap state
        state = {
            "amount_specified_remaining": amount_specified,
            "amount_calculated": 0,
            "sqrt_price_x96": slot0_start["sqrt_price_x96"],
            "tick": slot0_start["tick"],
            "fee_growth_global_x128": (
                self.fee_growth_global0_x128
                if zero_for_one
                else self.fee_growth_global1_x128
            ),
            "protocol_fee": 0,
            "liquidity": cache["liquidity_start"],
        }

        # Continue swapping until we're done or we hit the price limit
        while (
            state["amount_specified_remaining"] != 0
            and state["sqrt_price_x96"] != sqrt_price_limit_x96
        ):
            step = {
                "sqrt_price_start_x96": state["sqrt_price_x96"],
                "tick_next": 0,
                "initialized": False,
                "sqrt_price_next_x96": 0,
                "amount_in": 0,
                "amount_out": 0,
                "fee_amount": 0,
            }

            # Find the next initialized tick
            step["tick_next"], step["initialized"] = (
                self.tick_bitmap.next_initialized_tick_within_one_word(
                    state["tick"], self.tick_spacing, zero_for_one
                )
            )

            # Ensure we stay within tick bounds
            if step["tick_next"] < self.MIN_TICK:
                step["tick_next"] = self.MIN_TICK
            elif step["tick_next"] > self.MAX_TICK:
                step["tick_next"] = self.MAX_TICK

            # Get the square root price at the next tick
            step["sqrt_price_next_x96"] = self.tick_math.get_sqrt_ratio_at_tick(
                step["tick_next"]
            )

            # Determine the target price for this swap step
            target_price = sqrt_price_limit_x96
            if (
                zero_for_one and step["sqrt_price_next_x96"] < sqrt_price_limit_x96
            ) or (
                not zero_for_one and step["sqrt_price_next_x96"] > sqrt_price_limit_x96
            ):
                target_price = step["sqrt_price_next_x96"]

            # Compute the swap amounts for this step
            (
                state["sqrt_price_x96"],
                step["amount_in"],
                step["amount_out"],
                step["fee_amount"],
            ) = self.swap_math.compute_swap_step(
                state["sqrt_price_x96"],
                target_price,
                state["liquidity"],
                state["amount_specified_remaining"],
                self.fee,
            )

            # Update the remaining amounts
            if exact_input:
                state["amount_specified_remaining"] -= (
                    step["amount_in"] + step["fee_amount"]
                )
                state["amount_calculated"] -= step["amount_out"]
            else:
                state["amount_specified_remaining"] += step["amount_out"]
                state["amount_calculated"] += step["amount_in"] + step["fee_amount"]

            # Apply protocol fee if enabled
            if cache["fee_protocol"] > 0:
                delta = step["fee_amount"] // cache["fee_protocol"]
                step["fee_amount"] -= delta
                state["protocol_fee"] += delta

            # Update global fee tracker
            if state["liquidity"] > 0:
                state["fee_growth_global_x128"] += self.full_math.mul_div(
                    step["fee_amount"], self.Q128, state["liquidity"]
                )

            # Update state when we cross a tick
            if state["sqrt_price_x96"] == step["sqrt_price_next_x96"]:
                if step["initialized"]:
                    # Get the latest observation if needed
                    if not cache["computed_latest_observation"]:
                        (
                            cache["tick_cumulative"],
                            cache["seconds_per_liquidity_cumulative_x128"],
                        ) = self.observations.observe_single(
                            cache["block_timestamp"],
                            0,
                            slot0_start["tick"],
                            slot0_start["observation_index"],
                            cache["liquidity_start"],
                            slot0_start["observation_cardinality"],
                        )
                        cache["computed_latest_observation"] = True

                    # Cross the tick boundary
                    liquidity_net = self.ticks.cross(
                        step["tick_next"],
                        (
                            state["fee_growth_global_x128"]
                            if zero_for_one
                            else self.fee_growth_global0_x128
                        ),
                        (
                            self.fee_growth_global1_x128
                            if zero_for_one
                            else state["fee_growth_global_x128"]
                        ),
                        cache["seconds_per_liquidity_cumulative_x128"],
                        cache["tick_cumulative"],
                        cache["block_timestamp"],
                    )

                    # Flip sign if going leftward
                    if zero_for_one:
                        liquidity_net = -liquidity_net

                    # Update liquidity
                    state["liquidity"] = self.liquidity_math.add_delta(
                        state["liquidity"], liquidity_net
                    )

                # Update tick after crossing
                state["tick"] = (
                    step["tick_next"] - 1 if zero_for_one else step["tick_next"]
                )
            elif state["sqrt_price_x96"] != step["sqrt_price_start_x96"]:
                # Recompute the tick based on the new price
                state["tick"] = self.tick_math.get_tick_at_sqrt_ratio(
                    state["sqrt_price_x96"]
                )

        # Update oracle data if the tick changed
        # NOTE: This is optional for us
        if state["tick"] != slot0_start["tick"]:
            (observation_index, observation_cardinality) = self.observations.write(
                slot0_start["observation_index"],
                cache["block_timestamp"],
                slot0_start["tick"],
                cache["liquidity_start"],
                slot0_start["observation_cardinality"],
                slot0_start["observation_cardinality_next"],
            )

            # Update slot0 with all new values
            self.slot0["sqrt_price_x96"] = state["sqrt_price_x96"]
            self.slot0["tick"] = state["tick"]
            self.slot0["observation_index"] = observation_index
            self.slot0["observation_cardinality"] = observation_cardinality
        else:
            # Just update the price
            self.slot0["sqrt_price_x96"] = state["sqrt_price_x96"]

        # Update liquidity if it changed
        if cache["liquidity_start"] != state["liquidity"]:
            self.liquidity = state["liquidity"]

        # Update fee growth global and protocol fees
        # NOTE: This is optional for us
        if zero_for_one:
            self.fee_growth_global0_x128 = state["fee_growth_global_x128"]
            if state["protocol_fee"] > 0:
                self.protocol_fees["token0"] += state["protocol_fee"]
        else:
            self.fee_growth_global1_x128 = state["fee_growth_global_x128"]
            if state["protocol_fee"] > 0:
                self.protocol_fees["token1"] += state["protocol_fee"]

        # Calculate final amounts
        if zero_for_one == exact_input:
            amount0 = amount_specified - state["amount_specified_remaining"]
            amount1 = state["amount_calculated"]
        else:
            amount0 = state["amount_calculated"]
            amount1 = amount_specified - state["amount_specified_remaining"]

        # Transfer tokens and handle callbacks
        # if zero_for_one:
        #     if amount1 < 0:
        #         self.transfer_helper.safe_transfer(self.token1, recipient, -amount1)

        #     balance0_before = self.balance0()
        #     self.callback_handler.uniswap_v3_swap_callback(amount0, amount1, data)
        #     assert balance0_before + amount0 <= self.balance0(), "IIA"  # Insufficient input amount
        # else:
        #     if amount0 < 0:
        #         self.transfer_helper.safe_transfer(self.token0, recipient, -amount0)

        #     balance1_before = self.balance1()
        #     self.callback_handler.uniswap_v3_swap_callback(amount0, amount1, data)
        #     assert balance1_before + amount1 <= self.balance1(), "IIA"  # Insufficient input amount

        # Emit swap event (simulated in Python)
        self.emit_swap(
            recipient,
            amount0,
            amount1,
            state["sqrt_price_x96"],
            state["liquidity"],
            state["tick"],
        )

        # Unlock the pool
        self.slot0["unlocked"] = True

        return amount0, amount1

    def emit_swap(self, recipient, amount0, amount1, sqrt_price_x96, liquidity, tick):
        """
        Simulate emitting a Swap event

        Args:
            recipient: Address receiving the tokens
            amount0: Amount of token0 (signed)
            amount1: Amount of token1 (signed)
            sqrt_price_x96: New sqrt price
            liquidity: Current liquidity
            tick: Current tick
        """
        print(
            f"Swap Event: recipient={recipient}, amount0={amount0}, amount1={amount1}, "
            f"sqrtPriceX96={sqrt_price_x96}, liquidity={liquidity}, tick={tick}"
        )

    def _block_timestamp(self):
        """Get the current block timestamp (simulated)"""
        import time

        return int(time.time())


def example_swap():
    # Let's assume this is a ZORA_COIN/WETH pool
    ZORA_COIN_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    WETH_ADDRESS = "0x4200000000000000000000000000000000000006"

    # Create a new pool
    pool = UniswapV3Pool(
        ZORA_COIN_ADDRESS, WETH_ADDRESS, 3000, 200
    )  # 0.3% fee, 200 tick spacing

    # Initialize token balances for the example
    token_holdings = {
        ZORA_COIN_ADDRESS: 1000000000,  # 1,000 USDC (assuming 6 decimals)
        WETH_ADDRESS: 1000000000000000000,  # 1 WETH (18 decimals)
    }

    # Initialize pool token balances
    pool.set_token_balances(
        1000000000000, 1000000000000000000
    )  # Some existing liquidity

    # Initialize with slot0 data from 0xE020E67Cb76C780329d4c205578Aaa6d6478Fb2A on Base
    # Using real data from a USDC/WETH pool on Base mainnet
    pool.set_slot0(
        sqrt_price_x96=1192753682531438526279728462822,  # Approximated price
        tick=-200532,  # Current tick
        observation_index=123,  # Oracle index
        observation_cardinality=240,  # Oracle cardinality
        observation_cardinality_next=240,  # Next oracle cardinality
        fee_protocol=0,  # No protocol fee
        unlocked=True,  # Pool is unlocked
    )

    # Set liquidity
    pool.set_liquidity(1836218451513)  # Approximated liquidity

    # Set fee growth accumulators
    pool.set_fee_growth_globals(
        fee_growth_global0_x128=20133203123712334436549,
        fee_growth_global1_x128=1073741789988657433562,
    )

    # Set up basic tick data for the example
    # In a real implementation, we would need more comprehensive tick data
    tick_bitmap_data = {
        -4: 0x100000000000000000000000000000000,  # Some initialized ticks
        -3: 0x400000200001000000000000800000000,
        -2: 0x100040000000000400000000000000000,
        -1: 0x40000000000020000080010000000000,
        0: 0x800000000000000100000000000400000,
        1: 0x20000800000000000000040000000000,
        2: 0x80001000000000000000000000200000,
        3: 0x40000000080000000200000000000000,
    }

    ticks_data = {
        -204120: {
            "liquidity_gross": 100000000000,
            "liquidity_net": 100000000000,
            "fee_growth_outside0_x128": 0,
            "fee_growth_outside1_x128": 0,
            "tick_cumulative_outside": 0,
            "seconds_per_liquidity_outside_x128": 0,
            "seconds_outside": 0,
            "initialized": True,
        },
        -203460: {
            "liquidity_gross": 200000000000,
            "liquidity_net": -100000000000,
            "fee_growth_outside0_x128": 0,
            "fee_growth_outside1_x128": 0,
            "tick_cumulative_outside": 0,
            "seconds_per_liquidity_outside_x128": 0,
            "seconds_outside": 0,
            "initialized": True,
        },
        -201300: {
            "liquidity_gross": 900000000000,
            "liquidity_net": 900000000000,
            "fee_growth_outside0_x128": 10000000000000,
            "fee_growth_outside1_x128": 20000000000000,
            "tick_cumulative_outside": 1000000,
            "seconds_per_liquidity_outside_x128": 300000000,
            "seconds_outside": 3600,
            "initialized": True,
        },
        -199980: {
            "liquidity_gross": 1500000000000,
            "liquidity_net": -900000000000,
            "fee_growth_outside0_x128": 20000000000000,
            "fee_growth_outside1_x128": 40000000000000,
            "tick_cumulative_outside": 2000000,
            "seconds_per_liquidity_outside_x128": 600000000,
            "seconds_outside": 7200,
            "initialized": True,
        },
    }

    pool.set_tick_data(tick_bitmap_data, ticks_data)

    # Set up observations for the oracle
    current_time = pool._block_timestamp()
    observations_data = [
        {
            "block_timestamp": current_time - 3600,
            "tick_cumulative": -700000000,
            "seconds_per_liquidity_cumulative_X128": 3456789,
        },
        {
            "block_timestamp": current_time - 1800,
            "tick_cumulative": -740000000,
            "seconds_per_liquidity_cumulative_X128": 6789012,
        },
        {
            "block_timestamp": current_time,
            "tick_cumulative": -760000000,
            "seconds_per_liquidity_cumulative_X128": 9012345,
        },
    ]

    pool.set_observations(observations_data)

    # Print initial state
    print("Initial Pool State:")
    print(f"  Token0: {ZORA_COIN_ADDRESS} (USDC)")
    print(f"  Token1: {WETH_ADDRESS} (WETH)")
    print(f"  Price: {pool.slot0['sqrt_price_x96']}")
    print(f"  Tick: {pool.slot0['tick']}")
    print(f"  Liquidity: {pool.liquidity}")

    # Now let's swap 330,100 of token1 (WETH) for token0 (USDC)
    # We're doing an exact input swap of token1 for token0
    SWAP_AMOUNT = 330100  # 0.00033010 WETH (assuming 18 decimals)

    # Add token1 to user balance for the swap
    token_holdings[WETH_ADDRESS] += SWAP_AMOUNT

    # Calculate price limit (we'll use 0 for max slippage)
    sqrt_price_limit_x96 = pool.MIN_SQRT_RATIO + 1  # Just above the min price

    # The recipient address
    recipient = "0xMyWalletAddress"

    # Execute the swap (token1 to token0, so zero_for_one is False)
    zero_for_one = False  # WETH to USDC
    amount_specified = SWAP_AMOUNT  # Exact input

    print(f"\nExecuting swap of {SWAP_AMOUNT} WETH for USDC...")

    try:
        amount0, amount1 = pool.swap(
            recipient=recipient,
            zero_for_one=zero_for_one,
            amount_specified=amount_specified,
            sqrt_price_limit_x96=sqrt_price_limit_x96,
            data=b"",  # No additional data
        )

        print("\nSwap completed!")
        print(f"  USDC received: {-amount0}")  # Negative means user received
        print(f"  WETH paid: {amount1}")  # Positive means user paid
        print(f"  New price: {pool.slot0['sqrt_price_x96']}")
        print(f"  New tick: {pool.slot0['tick']}")

        # Calculate price
        price_x96 = (pool.slot0["sqrt_price_x96"] ** 2) / (1 << 192)
        price = price_x96 * (
            10**12
        )  # Adjust for USDC (6 decimals) and WETH (18 decimals)

        print(f"  New price in USDC per WETH: {price}")

    except Exception as e:
        print(f"Swap failed: {str(e)}")


# Run the example
example_swap()
