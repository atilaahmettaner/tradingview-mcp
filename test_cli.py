#!/usr/bin/env python3
"""
Smoke test for TradingView MCP CLI
Tests that the CLI entry point can be invoked and shows help.
"""

import subprocess
import sys


def test_cli_help():
    """Test that the CLI can be invoked with --help"""
    try:
        # Test via module invocation
        result = subprocess.run(
            [sys.executable, "-m", "tradingview_mcp.server", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            print(f"❌ CLI invocation failed with return code {result.returncode}")
            print(f"STDERR: {result.stderr}")
            return False
        
        # Check that help text contains expected content
        # We check for key command-line arguments to ensure the CLI is working
        expected_strings = ["--help", "stdio", "options"]
        for expected in expected_strings:
            if expected not in result.stdout:
                print(f"❌ Expected '{expected}' in help output")
                return False
        
        print("✅ CLI help test passed")
        print(f"Output preview: {result.stdout[:200]}...")
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ CLI invocation timed out")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False


def test_cli_import():
    """Test that the main function can be imported"""
    try:
        # Try importing the main function
        from tradingview_mcp.server import main
        
        if not callable(main):
            print("❌ main is not callable")
            return False
        
        print("✅ CLI import test passed")
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import main function: {e}")
        return False
    except Exception as e:
        print(f"❌ Import test failed with error: {e}")
        return False


def main():
    """Run all smoke tests"""
    print("🧪 Running TradingView MCP CLI smoke tests")
    print("=" * 60)
    
    tests = [
        ("Import test", test_cli_import),
        ("Help invocation test", test_cli_help),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        results.append(test_func())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All smoke tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
