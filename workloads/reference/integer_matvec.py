"""与硬件编码无关的稠密整数向量×矩阵参考；Python整数给出精确点积。"""


# 独立检查输入并按列做精确乘加；不量化、不截断，也不应用硬件输出溢出策略。
def reference_integer_matvec(vector: tuple[int, ...], matrix: tuple[tuple[int, ...], ...], *,
                             max_macs: int = 1_000_000) -> tuple[int, ...]:
    if type(max_macs) is not int or max_macs <= 0:
        raise ValueError("max_macs must be a positive integer")
    if not isinstance(vector, (tuple, list)) or not isinstance(matrix, (tuple, list)) or not vector or not matrix:
        raise TypeError("reference requires nonempty vector and matrix sequences")
    if any(not isinstance(row, (tuple, list)) for row in matrix) or not matrix[0]:
        raise ValueError("reference matrix rows must be nonempty sequences")
    columns = len(matrix[0])
    if len(vector) != len(matrix) or any(len(row) != columns for row in matrix):
        raise ValueError("reference MatVec shape mismatch")
    if len(vector) * columns > max_macs:
        raise ValueError("reference work exceeds max_macs")
    if any(type(v) is not int for v in vector) or any(type(v) is not int for row in matrix for v in row):
        raise TypeError("reference operands must be Python integers")
    return tuple(sum(vector[i] * matrix[i][j] for i in range(len(vector))) for j in range(columns))
