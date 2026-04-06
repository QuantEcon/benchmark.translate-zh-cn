"""Classify terms by difficulty level.

Categories:
- basic: Common terms from intro economics/math courses
- intermediate: Standard textbook terms requiring domain knowledge  
- advanced: Specialist or research-level terms

Run: uv run python scripts/classify_difficulty.py
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "terms"

# === BASIC terms: intro-level, taught in first-year courses ===
BASIC_TERMS = {
    # economics
    "Budget constraint", "Consumer surplus", "Cost function", "Discount factor",
    "Equilibrium", "Exogenous", "Market clearing", "Social welfare",
    "Capital depreciation", "Perfect foresight", "Dynamic model",
    # finance
    "Annuity", "Discounting", "Present value", "Money supply", "Money demand",
    "Volatility", "Spot price", "Money multiplier", "Present discounted value",
    "Corporate bond", "Mutual fund", "Underlying asset", "Strike price",
    "Gross rate of return", "Fiat money",
    # macroeconomics
    "Business cycle", "Closed economy", "GDP", "Gross Domestic Product",
    "Price level", "Recessions", "Expansions", "Aggregate consumption",
    "Fiscal policy multiplier", "Government expenditures multiplier",
    "Investment multiplier", "Marginal propensity to consume",
    "Marginal propensity to save", "Stagflation", "Domestic credit",
    "Industrial output", "Long-Run Growth",
    # mathematics
    "Calculus", "Complex number", "Convergence", "Euclidean distance",
    "Linear algebra", "Initial condition", "Complex plane", "Real part",
    "Imaginary part", "Complex conjugate", "Vertices",
    "Log transform", "Indicator function",
    # probability
    "Central limit theorem", "Conditional probability",
    "Cumulative distribution function", "Exponential distribution",
    "Normal distribution", "Probability density function",
    "Probability mass function", "Law of large numbers",
    "Independent and identically distributed", "Moments",
    "Marginal distribution", "Support", "Law of total probability",
    "Beta distribution",
    # statistics
    "Histogram", "Sample mean", "Sample variance", "OLS",
    "Ordinary Least Squares", "Scatter plot", "Time series", "Residuals",
    "Weighted average", "First Moment", "Central moment",
    "Empirical Distribution", "SSR", "Sum of the squared residuals",
    "Simple regression model",
    # optimization
    "Dynamic programming", "Linear programming", "Optimal path", "Optimal policy",
    # numerical-methods
    "Monte Carlo", "Numerical integration", "Vectorization",
    # stochastic-processes
    "Markov chain", "State space", "Stationary distribution",
    "Transition probability", "Stochastic matrix",
    # calculus
    "Partial derivative", "Taylor series",
    # game-theory
    "Zero-sum game",
    # microeconomics
    "Marginal revenue", "Producer surplus",
    # other
    "Exercise", "Lecture", "Violin plot",
    # dynamic-programming
    "State variable", "Steady state", "Finite horizon",
}

# === ADVANCED terms: specialist, research-level, or very niche ===
ADVANCED_TERMS = {
    # economics
    "Autarky equilibrium", "Geary–Khamis dollar", "Forward-looking difference equation",
    "Tax farming", "Equalizing Difference Model", "Welfare maximization problem",
    "Multiple consumer economy", "Jump variable", "Second fundamental welfare theorem",
    "Projected corporate tax revenue", "Money-financed government deficit",
    "Exogenous initial capital stock", "Dynamic Laffer curve",
    "Consumption-smoothing model", "Tax-smoothing model",
    # finance
    "Barrier option", "Knockout barrier", "Inflation-tax theory", "Real bills theory",
    "Stochastic volatility", "Unpleasant monetarist arithmetic",
    "Fiscal theory of price levels", "Legal restrictions theory",
    "Arrow securities", "State-contingent claims", "Risk-neutral pricing",
    "Fractional reserve banking", "Inflation-indexed bonds",
    # linear-algebra
    "Gershgorin Circle Theorem", "Perron-Frobenius theorem", "Perron projection",
    "Invariant subspace", "Eigenvector decomposition",
    # mathematics
    "Neumann Series Lemma", "de Moivre's theorem", "PageRank algorithm",
    "Hub centrality", "Authority centrality", "Katz centrality",
    "Vector linear difference equations", "Second-order linear difference equation",
    "Forcing variable", "Recursive expressions",
    # macroeconomics
    "OLG model", "Overlapping generations model", "Multiplier-accelerator model",
    "Solow-Swan Growth Model", "Golden Rule savings rate",
    "Aggregate supply of capital", "Time to build",
    # stochastic-processes
    "Accessible state", "Communicating states", "Jump Chain Algorithm",
    "Ergodicity",
    # statistics
    "Kolmogorov-Smirnov test", "Silverman's rule",
    "Non-stationary univariate time series",
    # probability
    "Bivariate uniform distribution", "Characteristic function",
    "Convergence in distribution", "Heavy-tailed distribution",
    "Light-tailed distribution", "Moment generating function",
    "Pareto tail", "Power law", "Tail index", "CCDF", "Counter CDF",
    # game-theory
    "Folk theorem", "Grim trigger strategy",
    # calculus
    "Angle sum identities", "Trigonometric integrals",
    # numerical-methods
    "Method of successive approximations", "Path simulation",
    # economics misc
    "Cobweb model", "Input-output model", "Lake model",
    "Cyclical price dynamics", "Distribution dynamics",
    "Financial repression", "Seigniorage",
    # other
    "FRED", "Federal Reserve Economic Data", "NBER",
    "National Bureau of Economic Research", "Survey of Consumer Finances",
    "Balance sheet equation",
}

# Everything else is intermediate (the default)


def classify():
    basic_count = 0
    intermediate_count = 0
    advanced_count = 0
    
    for filepath in sorted(DATA_DIR.glob("_seed_*.json")):
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        # Handle both bare list and {version, entries} wrapper
        if isinstance(raw, dict) and "entries" in raw:
            data = raw["entries"]
            wrapper = raw
        else:
            data = raw
            wrapper = None
        changed = False
        
        for term in data:
            en = term["en"]
            old_diff = term.get("difficulty")
            
            if en in BASIC_TERMS:
                new_diff = "basic"
            elif en in ADVANCED_TERMS:
                new_diff = "advanced"
            else:
                new_diff = "intermediate"
            
            if old_diff != new_diff:
                term["difficulty"] = new_diff
                changed = True
            
            if new_diff == "basic":
                basic_count += 1
            elif new_diff == "advanced":
                advanced_count += 1
            else:
                intermediate_count += 1
        
        if changed:
            output = wrapper if wrapper else data
            filepath.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"  Updated {filepath.name}")
    
    total = basic_count + intermediate_count + advanced_count
    print(f"\nClassification complete:")
    print(f"  basic:        {basic_count:3d} ({basic_count/total:.0%})")
    print(f"  intermediate: {intermediate_count:3d} ({intermediate_count/total:.0%})")
    print(f"  advanced:     {advanced_count:3d} ({advanced_count/total:.0%})")
    print(f"  total:        {total}")
    
    # Verify all terms in our sets actually exist
    all_en = set()
    for filepath in sorted(DATA_DIR.glob("_seed_*.json")):
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        data = raw["entries"] if isinstance(raw, dict) and "entries" in raw else raw
        for term in data:
            all_en.add(term["en"])
    
    missing_basic = BASIC_TERMS - all_en
    missing_advanced = ADVANCED_TERMS - all_en
    if missing_basic:
        print(f"\n⚠ Basic terms not found in dataset: {missing_basic}")
    if missing_advanced:
        print(f"\n⚠ Advanced terms not found in dataset: {missing_advanced}")


if __name__ == "__main__":
    classify()
