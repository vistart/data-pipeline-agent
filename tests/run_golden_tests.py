"""Test runner for golden test cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tests.golden_cases import load_golden_set


def run_test_case(case: dict, agent=None, verbose: bool = False) -> dict:
    """运行单个测试用例"""
    result = {
        "name": case["name"],
        "category": case["category"],
        "status": "pending",
        "checks": [],
    }

    try:
        if agent is None:
            # 模拟模式：只验证输入格式
            result["status"] = "skip"
            result["checks"].append("Agent not provided, skipping execution")
            return result

        from dpa.sessions import Session

        session = Session(name=f"test_{case['name']}")
        response = agent.run(case["input"], session)

        # 验证响应
        validation = case.get("validation", {})

        # 检查响应必须包含的内容
        if "response_must_contain" in validation:
            for keyword in validation["response_must_contain"]:
                if keyword.lower() in response.lower():
                    result["checks"].append(f"✅ Response contains '{keyword}'")
                else:
                    result["checks"].append(f"❌ Response missing '{keyword}'")
                    result["status"] = "fail"

        # 检查不应包含的内容
        if "response_must_not_contain" in validation:
            for keyword in validation["response_must_not_contain"]:
                if keyword.lower() in response.lower():
                    result["checks"].append(f"❌ Response contains forbidden '{keyword}'")
                    result["status"] = "fail"
                else:
                    result["checks"].append(f"✅ Response does not contain '{keyword}'")

        # 检查工具调用
        if "must_call_tools" in validation:
            tool_calls = session.messages()
            called_tools = [m.get("tool") for m in tool_calls if m.get("role") == "tool_call"]
            for tool in validation["must_call_tools"]:
                if tool in called_tools:
                    result["checks"].append(f"✅ Called tool '{tool}'")
                else:
                    result["checks"].append(f"❌ Did not call tool '{tool}'")
                    result["status"] = "fail"

        if result["status"] == "pending":
            result["status"] = "pass"

    except Exception as e:
        result["status"] = "error"
        result["checks"].append(f"❌ Exception: {str(e)}")

    return result


def run_golden_tests(category: str = "all", verbose: bool = False) -> list[dict]:
    """运行黄金集测试"""
    results = []

    if category == "all":
        categories = ["normal", "edge", "malicious"]
    else:
        categories = [category]

    for cat in categories:
        cases = load_golden_set(cat)
        print(f"\n{'='*60}")
        print(f"Running {cat} cases ({len(cases)} total)")
        print(f"{'='*60}")

        for case in cases:
            result = run_test_case(case, verbose=verbose)
            results.append(result)

            status_icon = {"pass": "✅", "fail": "❌", "error": "💥", "skip": "⏭️"}.get(
                result["status"], "❓"
            )
            print(f"  {status_icon} {result['name']}")

            if verbose:
                for check in result["checks"]:
                    print(f"    {check}")

    # 汇总
    print(f"\n{'='*60}")
    print(f"Summary")
    print(f"{'='*60}")

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skip")

    print(f"  Total: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Errors: {errors}")
    print(f"  Skipped: {skipped}")

    if total > 0:
        print(f"  Pass rate: {passed/total*100:.1f}%")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run golden test cases")
    parser.add_argument("--category", default="all", choices=["all", "normal", "edge", "malicious"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    results = run_golden_tests(category=args.category, verbose=args.verbose)

    # 保存结果
    output_path = Path("test_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_path}")
