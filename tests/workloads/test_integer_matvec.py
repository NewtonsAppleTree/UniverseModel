"""独立整数MatVec参考不依赖任何CIM量化或硬件模型。"""

import unittest

from workloads.reference.integer_matvec import reference_integer_matvec


# 精确点积、形状和材料化预算是参考自身的契约。
class IntegerMatvecTests(unittest.TestCase):
    # 含负权重/负输入及超过binary64精度的整数，均保持Python整数精确性。
    def test_exact_integer_products(self):
        self.assertEqual(reference_integer_matvec((3, 5), ((1, -2, 5), (-3, 4, -1))), (-12, 14, 10))
        self.assertEqual(reference_integer_matvec((2**60 + 1, -2**60), ((1,), (1,))), (1,))

    # 错误shape和bool/实数不借由隐式转换进入数值参考。
    def test_input_contracts(self):
        for vector, matrix in (((), ()), ("1", ((1,),)), ((1,), ((1,), (2,))),
                               ((1, 2), ((1,), (2, 3))), ((True,), ((1,),)), ((1,), ((0.5,),))):
            with self.assertRaises((ValueError, TypeError)):
                reference_integer_matvec(vector, matrix)

    # 宿主限制不是资源数量；边界等于MAC数可运行。
    def test_host_work_limit(self):
        self.assertEqual(reference_integer_matvec((2, 3), ((4,), (5,)), max_macs=2), (23,))
        with self.assertRaises(ValueError):
            reference_integer_matvec((2, 3), ((4,), (5,)), max_macs=1)


if __name__ == "__main__":
    unittest.main()
