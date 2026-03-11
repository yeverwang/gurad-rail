"""
contract_loader.py — YAML 合约加载器
负责：读取文件 → 结构校验(Pydantic) → 激活状态检查 → 返回 Contract 对象
"""
from __future__ import annotations
import yaml
from pathlib import Path
from .models import Contract


class ContractLoadError(Exception):
    pass


class ContractLoader:

    @staticmethod
    def load(path: str | Path) -> Contract:
        """
        从文件路径加载合约，完成：
        1. YAML 解析
        2. Pydantic Schema 校验
        3. 状态检查（suspended/deprecated 合约拒绝加载）
        """
        p = Path(path)
        if not p.exists():
            raise ContractLoadError(f"合约文件不存在: {p}")

        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ContractLoadError(f"YAML 解析失败: {e}") from e

        try:
            contract = Contract.model_validate(raw)
        except Exception as e:
            raise ContractLoadError(f"合约 Schema 校验失败: {e}") from e

        status = contract.metadata.status
        if status in ("suspended", "deprecated"):
            raise ContractLoadError(
                f"合约 [{contract.metadata.contract_id}] 状态为 '{status}'，拒绝加载"
            )

        return contract

    @staticmethod
    def load_from_dict(data: dict) -> Contract:
        """从字典加载合约（用于测试或动态加载）"""
        try:
            return Contract.model_validate(data)
        except Exception as e:
            raise ContractLoadError(f"合约 Schema 校验失败: {e}") from e
