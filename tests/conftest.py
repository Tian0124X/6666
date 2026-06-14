"""pytest 全局 fixtures"""

import pytest
from unittest.mock import Mock, patch
import pandas as pd


@pytest.fixture
def mock_llm():
    """模拟 LLM 响应，避免测试中调用真实 API"""
    with patch("langchain_openai.ChatOpenAI") as mock:
        instance = Mock()
        instance.invoke.return_value = Mock(content="这是一个模拟的 LLM 回答。")
        mock.return_value = instance
        yield mock


@pytest.fixture
def sample_dataframe() -> pd.DataFrame:
    """测试用 DataFrame"""
    return pd.DataFrame({
        "月份": ["1月", "2月", "3月", "4月"],
        "销售额": [10000, 15000, 12000, 18000],
        "成本": [6000, 8000, 7000, 9000],
    })


@pytest.fixture
def sample_dataframe_with_missing() -> pd.DataFrame:
    """含缺失值的测试 DataFrame"""
    import numpy as np
    return pd.DataFrame({
        "A": [1.0, None, 3.0, 4.0],
        "B": [5.0, 6.0, None, 8.0],
    })


@pytest.fixture
def sample_dataframe_with_duplicates() -> pd.DataFrame:
    """含重复行的测试 DataFrame"""
    return pd.DataFrame({"A": [1, 1, 2, 3], "B": [4, 4, 5, 6]})
