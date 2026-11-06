"""位权累加的独立数值参考；只在最终输出执行有符号溢出策略。"""

from chipmodel.common import count


# y=Σ partial_i*2^shift_i；先用无限精度整数累加，再按 width_bits 做 error/saturate/wrap。
def shift_accumulate(partials: tuple[int, ...], shifts: tuple[int, ...], *,
                     width_bits: int, overflow: str) -> int:
    count("width_bits", width_bits)
    if width_bits > 64:
        raise ValueError("width_bits must be <=64 in this reference")
    if len(partials) != len(shifts):
        raise ValueError("partials and shifts must have the same length")
    if overflow not in ("error", "saturate", "wrap"):
        raise ValueError("overflow must be error, saturate or wrap")
    for value, shift in zip(partials, shifts):
        if type(value) is not int:
            raise TypeError("partials must contain Python ints")
        count("shift", shift, 0)
        if shift >= 64:
            raise ValueError("shift must be <64 in this reference")
    total = sum(value << shift for value, shift in zip(partials, shifts))
    lower, upper = -(1 << (width_bits - 1)), (1 << (width_bits - 1)) - 1
    if lower <= total <= upper:
        return total
    if overflow == "error":
        raise ValueError("accumulated result exceeds signed output width")
    if overflow == "saturate":
        return min(upper, max(lower, total))
    return (total - lower) % (1 << width_bits) + lower
