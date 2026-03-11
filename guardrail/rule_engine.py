"""
rule_engine.py — 安全规则表达式求值器
基于 Python AST，不使用 eval()，支持：
  - 比较运算: ==  !=  <  <=  >  >=
  - 逻辑运算: AND  OR  NOT
  - 成员判断: IN  NOT IN
  - 算术运算: +  -  *  /
  - 点属性访问: transfer.amount  (映射为 transfer__amount)
  - 布尔字面量: True / False
"""
from __future__ import annotations
import ast
import operator
from typing import Any


class RuleEngineError(Exception):
    pass


class SafeEvaluator(ast.NodeVisitor):
    """
    受限 AST 求值器
    只允许白名单节点类型，拒绝任何函数调用、属性方法等
    """

    # 允许的比较操作符
    _CMP_OPS = {
        ast.Eq:    operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt:    operator.lt,
        ast.LtE:   operator.le,
        ast.Gt:    operator.gt,
        ast.GtE:   operator.ge,
        ast.In:    lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }

    # 允许的布尔操作符
    _BOOL_OPS = {
        ast.And: all,
        ast.Or:  any,
    }

    # 允许的算术操作符
    _BIN_OPS = {
        ast.Add:  operator.add,
        ast.Sub:  operator.sub,
        ast.Mult: operator.mul,
        ast.Div:  operator.truediv,
    }

    def __init__(self, namespace: dict[str, Any]):
        self.namespace = namespace

    def evaluate(self, expr: str) -> Any:
        """
        对外接口：传入规则字符串，返回求值结果
        """
        try:
            # 预处理：将点属性访问转为下划线命名空间查找
            # "transfer.amount" → "transfer__amount"
            # 注意：只转换 word.word 模式，不影响字符串内容
            normalized = self._normalize_dot_access(expr)
            tree = ast.parse(normalized, mode='eval')
            return self.visit(tree.body)
        except RuleEngineError:
            raise
        except Exception as e:
            raise RuleEngineError(f"规则解析失败: '{expr}' — {e}") from e

    def _normalize_dot_access(self, expr: str) -> str:
        """
        两步预处理：
        1. 大写关键词 → Python 小写关键词
           AND→and, OR→or, NOT IN→not in, NOT→not, IN→in, True/False 保持
        2. 'obj.attr' → 'obj__attr'
        """
        import re
        # Step1: 关键词大小写规范化（仅替换单词边界处的关键词）
        # 顺序很重要：先替换 NOT IN（两词），再替换单词 NOT/AND/OR/IN
        result = expr
        result = re.sub(r'\bNOT\s+IN\b', 'not in', result)
        result = re.sub(r'\bAND\b', 'and', result)
        result = re.sub(r'\bOR\b',  'or',  result)
        result = re.sub(r'\bNOT\b', 'not', result)
        result = re.sub(r'\bIN\b',  'in',  result)
        # Step2: 点属性访问 → 下划线命名
        result = re.sub(r'\b([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\b', r'\1__\2', result)
        return result

    # ── 节点访问器 ──────────────────────────────

    def visit_Expression(self, node): return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float, str, bool, type(None))):
            return node.value
        raise RuleEngineError(f"不允许的常量类型: {type(node.value)}")

    def visit_NameConstant(self, node):   # Python 3.7 兼容
        return node.value

    def visit_Name(self, node):
        name = node.id
        if name in ('True', 'False', 'None'):
            return {'True': True, 'False': False, 'None': None}[name]
        if name in self.namespace:
            return self.namespace[name]
        raise RuleEngineError(f"未定义的变量: '{name}'")

    def visit_Num(self, node): return node.n   # Python 3.7 兼容

    def visit_Str(self, node): return node.s   # Python 3.7 兼容

    def visit_List(self, node):
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node):
        return tuple(self.visit(e) for e in node.elts)

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Not):
            return not self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -self.visit(node.operand)
        raise RuleEngineError(f"不允许的一元操作: {type(node.op)}")

    def visit_BoolOp(self, node):
        op_func = self._BOOL_OPS.get(type(node.op))
        if op_func is None:
            raise RuleEngineError(f"不允许的布尔操作: {type(node.op)}")
        values = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)

    def visit_BinOp(self, node):
        op_func = self._BIN_OPS.get(type(node.op))
        if op_func is None:
            raise RuleEngineError(f"不允许的算术操作: {type(node.op)}")
        left  = self.visit(node.left)
        right = self.visit(node.right)
        return op_func(left, right)

    def visit_Compare(self, node):
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            op_func = self._CMP_OPS.get(type(op))
            if op_func is None:
                raise RuleEngineError(f"不允许的比较操作: {type(op)}")
            right = self.visit(comparator)
            if not op_func(left, right):
                return False
            left = right
        return True

    def generic_visit(self, node):
        raise RuleEngineError(
            f"不允许的表达式节点: {type(node).__name__} — "
            f"规则引擎仅支持基础比较/逻辑/算术运算"
        )


def evaluate_rule(rule: str, namespace: dict[str, Any]) -> bool:
    """
    便捷函数：对外统一入口
    - rule: 规则表达式字符串
    - namespace: 变量命名空间（来自 EvaluationContext.to_namespace()）
    返回 True = 规则满足（合规），False = 规则不满足（违规）
    """
    evaluator = SafeEvaluator(namespace)
    result = evaluator.evaluate(rule)
    return bool(result)
