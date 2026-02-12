# 🤝 Contributing to TradingView MCP Server

Thank you for your interest in contributing to the TradingView MCP Server! This project aims to provide the best market analysis tools for AI assistants and traders.

## 🌟 Ways to Contribute

### 🐛 Report Bugs
- Found a bug? [Open an issue](https://github.com/atilaahmettaner/tradingview-mcp/issues/new)
- Include reproduction steps, expected vs actual behavior
- Provide system info (OS, Python version, UV version)

### 💡 Suggest Features
- Have an idea? [Create a feature request](https://github.com/atilaahmettaner/tradingview-mcp/issues/new)
- Explain the use case and expected benefit
- Consider implementation complexity

### 📝 Improve Documentation  
- Fix typos, improve clarity, add examples
- Update installation guides for new platforms
- Add troubleshooting scenarios

### 💻 Code Contributions
- Fix bugs, implement features, optimize performance
- Follow our coding standards and testing guidelines
- Submit pull requests with clear descriptions

## 🚀 Getting Started

### 1. Fork & Clone
```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR-USERNAME/tradingview-mcp.git
cd tradingview-mcp
```

### 2. Set Up Development Environment
```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Install development dependencies
uv sync --dev
```

### 3. Run Tests
```bash
# Run the test suite
uv run pytest

# Run linting
uv run ruff check

# Run type checking
uv run mypy src/
```

### 4. Test Your Changes
```bash
# Test the server locally
uv run python src/tradingview_mcp/server.py

# Test with MCP Inspector
uv run mcp dev src/tradingview_mcp/server.py

# Run integration tests
uv run python test_api.py
```

## 📋 Development Guidelines

### Code Style
- **Python Style:** Follow PEP 8 with our customizations
- **Linting:** Use Ruff for code formatting and linting
- **Type Hints:** Add type annotations for all new functions
- **Docstrings:** Document all public functions and classes

### Code Organization
```
src/tradingview_mcp/
├── server.py              # Main MCP server
├── core/                  # Core business logic
│   ├── services/         # Market data services
│   ├── utils/           # Utility functions
│   └── indicators/      # Technical indicators
├── coinlist/            # Exchange symbol lists
└── __init__.py
```

### Naming Conventions
- **Functions:** `snake_case` (e.g., `get_top_gainers`)
- **Classes:** `PascalCase` (e.g., `MarketAnalyzer`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `DEFAULT_LIMIT`)
- **Files:** `snake_case.py` (e.g., `market_utils.py`)

## 🧪 Testing Standards

### Unit Tests
```python
# Example test structure
import pytest
from src.tradingview_mcp.server import top_gainers

def test_top_gainers_basic():
    """Test basic top_gainers functionality"""
    result = top_gainers(exchange="KUCOIN", limit=5)
    
    assert "symbols" in result
    assert len(result["symbols"]) <= 5
    assert result["exchange"] == "KUCOIN"

def test_top_gainers_invalid_exchange():
    """Test error handling for invalid exchange"""
    result = top_gainers(exchange="INVALID")
    assert "error" in result
```

### Integration Tests
```python
def test_real_market_data():
    """Test with real market data (requires internet)"""
    result = top_gainers(exchange="KUCOIN", timeframe="1D", limit=3)
    
    # Should get real data
    assert "symbols" in result
    assert len(result["symbols"]) > 0
    
    # Validate data structure
    for symbol in result["symbols"]:
        assert "symbol" in symbol
        assert "changePercent" in symbol
        assert isinstance(symbol["changePercent"], (int, float))
```

### Test Coverage
- Aim for >80% code coverage
- Test both success and error paths
- Include edge cases and boundary conditions

## 🔧 Common Development Tasks

### Adding a New Exchange
1. **Update Exchange Lists:**
   ```python
   # In core/utils/validators.py
   EXCHANGE_SCREENER = {
       "NEW_EXCHANGE": "crypto",  # or "america", "turkey"
       # ... existing exchanges
   }
   ```

2. **Add Symbol List:**
   ```bash
   # Create coinlist/new_exchange.txt
   echo "BTCUSDT\nETHUSDT\n..." > coinlist/new_exchange.txt
   ```

3. **Test Integration:**
   ```python
   # Test the new exchange
   result = top_gainers(exchange="NEW_EXCHANGE")
   ```

### Adding New Technical Indicators
1. **Create Indicator Function:**
   ```python
   # In core/indicators/custom.py
   def calculate_custom_indicator(prices: List[float]) -> float:
       """Calculate custom technical indicator"""
       # Implementation here
       return result
   ```

2. **Integrate in Analysis:**
   ```python
   # In server.py coin_analysis function
   custom_value = calculate_custom_indicator(price_data)
   result["technical_indicators"]["custom"] = custom_value
   ```

### Adding New Markets
1. **Research TradingView Markets:**
   - Check available markets in tradingview-screener
   - Test data availability and reliability

2. **Update Market Mappings:**
   ```python
   # Add market configuration
   MARKET_CONFIGS = {
       "NEW_MARKET": {
           "screener": "new_market_code",
           "timeframes": ["5m", "15m", "1h", "1D"],
           "supported_symbols": ["SYMBOL1", "SYMBOL2"]
       }
   }
   ```

## 📖 Documentation Standards

### Function Documentation
```python
def analyze_bollinger_bands(
    symbol: str,
    exchange: str = "KUCOIN", 
    timeframe: str = "1D"
) -> dict:
    """Analyze Bollinger Bands for a specific symbol.
    
    Provides comprehensive Bollinger Band analysis including band width,
    position relative to bands, and trading signals.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT", "AAPL")
        exchange: Exchange name (KUCOIN, BINANCE, etc.)
        timeframe: Time interval (5m, 15m, 1h, 4h, 1D, 1W, 1M)
        
    Returns:
        dict: Analysis results containing:
            - band_width: Float indicating volatility
            - position: String describing price position
            - signal: Trading signal (BUY, SELL, NEUTRAL)
            - rating: Integer rating (-3 to +3)
            
    Raises:
        ValueError: If symbol format is invalid
        RuntimeError: If exchange data is unavailable
        
    Examples:
        >>> analyze_bollinger_bands("BTCUSDT", "KUCOIN", "1D")
        {
            "band_width": 0.0342,
            "position": "upper_50_percent", 
            "signal": "BUY",
            "rating": 2
        }
    """
```

### README Updates
- Keep installation instructions current
- Update feature lists when adding capabilities
- Include new usage examples
- Maintain troubleshooting section

## 🔍 Code Review Process

### Before Submitting PR:
1. **Self Review:**
   - Run all tests locally
   - Check code formatting with Ruff
   - Verify type hints with MyPy
   - Test edge cases manually

2. **PR Description:**
   ```markdown
   ## Summary
   Brief description of changes

   ## Changes Made
   - Added new exchange support for XYZ
   - Fixed bug in Bollinger Band calculation
   - Updated documentation

   ## Testing
   - [ ] Unit tests pass
   - [ ] Integration tests pass  
   - [ ] Manual testing completed
   - [ ] Documentation updated

   ## Breaking Changes
   None / List any breaking changes
   ```

### Review Criteria:
- **Functionality:** Does it work as intended?
- **Performance:** No significant slowdowns
- **Security:** No sensitive data exposure
- **Maintainability:** Clean, readable code
- **Documentation:** Proper docs and examples

## 🚀 Release Process

### Version Numbering
We follow [Semantic Versioning](https://semver.org/):
- **Major (X.0.0):** Breaking changes
- **Minor (0.X.0):** New features, backward compatible
- **Patch (0.0.X):** Bug fixes, backward compatible

### Release Checklist:
1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Run full test suite
4. Create release tag
5. Create GitHub release (triggers automatic publishing to GitHub Packages)
6. Update documentation
7. Announce in community channels

**Note:** Publishing to GitHub Packages happens automatically via GitHub Actions when you create a GitHub release. Ensure the version in `pyproject.toml` is updated before creating the release, as GitHub Packages does not allow version overwrites.

## 🏆 Recognition

### Contributors Hall of Fame
We recognize valuable contributions:
- Code contributors in AUTHORS.md
- Documentation improvements acknowledged
- Bug reporters credited in release notes
- Feature requesters mentioned in changelogs

### Contribution Levels:
- 🥉 **Bronze:** 1-5 merged PRs
- 🥈 **Silver:** 6-15 merged PRs  
- 🥇 **Gold:** 16+ merged PRs or major features
- 💎 **Diamond:** Core maintainers

## 📞 Getting Help

### Development Questions:
1. **Check existing issues** for similar questions
2. **GitHub Discussions** for general development chat
3. **Discord/Slack** for real-time help (if available)
4. **Email maintainers** for sensitive issues

### Common Questions:
- **How to debug API rate limits?** Use MCP Inspector with verbose logging
- **Adding new timeframes?** Check TradingView screener support first  
- **Performance optimization?** Focus on reducing API calls and caching

## 🎯 Project Goals

### Short-term (Q1 2025):
- [ ] Add support for 5 more exchanges
- [ ] Implement advanced pattern recognition
- [ ] Improve error handling and fallbacks
- [ ] Add comprehensive test suite

### Long-term (2025):
- [ ] Real-time WebSocket data feeds
- [ ] Custom indicator framework
- [ ] Portfolio tracking capabilities
- [ ] Advanced backtesting tools

## 📜 Code of Conduct

### Our Standards:
- **Be respectful** to all contributors
- **Be inclusive** - welcome newcomers
- **Be constructive** in feedback
- **Be patient** with learning curves

### Unacceptable Behavior:
- Harassment or discrimination
- Trolling or inflammatory comments
- Spam or off-topic discussions
- Sharing proprietary trading strategies without permission

---

**Thank you for contributing to the TradingView MCP Server! Together, we're building the future of AI-powered market analysis. 🚀📈**
