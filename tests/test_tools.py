"""工具系统测试"""

import os
import pytest
import pandas as pd
from app.tools.base import registry, ToolRegistry


class TestToolRegistry:
    """工具注册中心测试"""

    def test_registry_singleton(self):
        """注册中心应为单例"""
        r1 = ToolRegistry()
        r2 = ToolRegistry()
        assert r1 is r2

    def test_registry_has_tools(self):
        """导入工具模块后注册中心应有工具"""
        names = registry.list_tool_names()
        assert "data_analyzer" in names
        assert "oa_query" in names
        assert "crm_query" in names

    def test_get_tool(self):
        """应能通过名称获取工具实例"""
        tool = registry.get_tool("oa_query")
        assert tool is not None
        assert tool.name == "oa_query"

    def test_get_nonexistent_tool(self):
        """获取不存在的工具应返回 None"""
        assert registry.get_tool("nonexistent") is None


class TestDataAnalyzer:
    """数据分析工具测试"""

    def test_load_csv(self, tmp_path):
        """应能正确加载 CSV 文件"""
        from app.tools.data_analyzer import DataAnalyzerTool
        df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        file_path = os.path.join(tmp_path, "test.csv")
        df.to_csv(file_path, index=False)

        tool = DataAnalyzerTool()
        loaded = tool._load_data(file_path)
        assert len(loaded) == 3
        assert list(loaded.columns) == ["A", "B"]

    def test_clean_drop_duplicates(self):
        """去重测试"""
        from app.tools.data_analyzer import DataAnalyzerTool
        df = pd.DataFrame({"A": [1, 1, 2, 3], "B": [4, 4, 5, 6]})
        tool = DataAnalyzerTool()
        cleaned = tool._clean_data(df)
        assert len(cleaned) == 3

    def test_clean_fill_median(self):
        """中位数填充测试"""
        from app.tools.data_analyzer import DataAnalyzerTool
        import numpy as np
        df = pd.DataFrame({"A": [1.0, np.nan, 3.0, 4.0], "B": [5.0, 6.0, np.nan, 8.0]})
        tool = DataAnalyzerTool()
        cleaned = tool._clean_data(df)
        assert cleaned["A"].isna().sum() == 0
        assert cleaned["B"].isna().sum() == 0

    def test_summary_output(self, tmp_path):
        """摘要生成输出应包含关键信息"""
        from app.tools.data_analyzer import DataAnalyzerTool
        df = pd.DataFrame({"月份": ["1月", "2月"], "销售额": [10000, 15000]})
        file_path = os.path.join(tmp_path, "test.csv")
        df.to_csv(file_path, index=False)

        tool = DataAnalyzerTool()
        df_loaded = tool._load_data(file_path)
        result = tool._generate_summary(df_loaded)
        assert "数据概览" in result
        assert "10000" in result

    def test_generate_chart(self, tmp_path):
        """图表生成应返回有效路径"""
        from app.tools.data_analyzer import DataAnalyzerTool
        df = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": [10, 20, 30, 40, 50]})
        tool = DataAnalyzerTool()
        chart_path = tool._generate_chart(df, "A", "bar", output_dir=str(tmp_path))
        assert chart_path is not None
        assert os.path.exists(chart_path)

    def test_generate_word_report(self, tmp_path):
        """Word 报告生成应返回有效路径"""
        from app.tools.data_analyzer import DataAnalyzerTool
        df = pd.DataFrame({"A": [1, 2, 3]})
        tool = DataAnalyzerTool()
        summary = tool._generate_summary(df)
        report_path = tool._generate_word_report(df, summary, [], output_dir=str(tmp_path))
        assert report_path is not None
        assert os.path.exists(report_path)
        assert report_path.endswith(".docx")


class TestOATool:
    """OA 工具测试"""

    def test_list_approvals(self):
        from app.tools.oa_crm import OATool
        tool = OATool()
        result = tool._query_mock("list_approvals", None)
        assert "OA-001" in result
        assert "年假申请" in result

    def test_query_by_user(self):
        from app.tools.oa_crm import OATool
        tool = OATool()
        result = tool._query_mock("query_by_user", "张三")
        assert "年假申请" in result
        assert "加班申请" in result
        assert "报销申请" not in result

    def test_query_by_status(self):
        from app.tools.oa_crm import OATool
        tool = OATool()
        result = tool._query_mock("query_by_status", "已驳回")
        assert "采购申请" in result
        assert "赵六" in result
        assert "年假申请" not in result

    def test_no_match(self):
        from app.tools.oa_crm import OATool
        tool = OATool()
        result = tool._query_mock("query_by_user", "不存在")
        assert "未找到" in result


class TestCRMTool:
    """CRM 工具测试"""

    def test_list_customers(self):
        from app.tools.oa_crm import CRMTool
        tool = CRMTool()
        result = tool._query_mock("list_customers", None)
        assert "ABC科技有限公司" in result
        assert "CRM-001" in result

    def test_query_by_industry(self):
        from app.tools.oa_crm import CRMTool
        tool = CRMTool()
        result = tool._query_mock("query_by_industry", "互联网")
        assert "ABC科技" in result
        assert "DEF信息技术" in result
        assert "XYZ实业" not in result

    def test_query_by_level(self):
        from app.tools.oa_crm import CRMTool
        tool = CRMTool()
        result = tool._query_mock("query_by_level", "A")
        assert "ABC科技" in result
        assert "DEF信息技术" in result
        assert "123商贸" not in result

    def test_no_match(self):
        from app.tools.oa_crm import CRMTool
        tool = CRMTool()
        result = tool._query_mock("query_by_industry", "金融")
        assert "未找到" in result


class TestSafety:
    """安全沙箱测试"""

    def test_path_traversal_blocked(self):
        from app.tools.registry import validate_file_path
        with pytest.raises(ValueError):
            validate_file_path("../../../etc/passwd")

    def test_windows_system_blocked(self):
        from app.tools.registry import validate_file_path
        with pytest.raises(ValueError):
            validate_file_path("C:\\Windows\\System32\\config")

    def test_shell_injection_blocked(self):
        from app.tools.registry import validate_file_path
        with pytest.raises(ValueError):
            validate_file_path("/data/doc; rm -rf /")
