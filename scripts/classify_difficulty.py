"""Classify terms by difficulty level.

Rubric:
- basic: High school level — AP Economics, AP Statistics, AP Calculus,
  precalculus, basic finance concepts
- intermediate: Undergraduate level — econ/math/stats/finance major courses
- advanced: Graduate level — PhD coursework, research-level, specialist theory

Run: uv run python scripts/classify_difficulty.py
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "terms"

# === BASIC terms: high school level (AP Econ, AP Stats, AP Calc, precalc, basic finance) ===
BASIC_TERMS = {
    # economics (AP Econ)
    "Budget constraint", "Capital depreciation", "Consumer surplus",
    "Cost function", "Equilibrium", "Market clearing", "Social welfare",
    # finance (basic finance / AP Econ)
    "Annuity", "Corporate bond", "Discounting", "Expiry date",
    "Money demand", "Money supply", "Mutual fund",
    "Present discounted value", "Present value", "Spot price",
    "Strike price", "Underlying asset", "Volatility",
    # macroeconomics (AP Macro)
    "Business cycle", "Closed economy", "Expansions", "GDP",
    "Gross Domestic Product", "Industrial output", "Price level",
    "Recessions", "Stagflation",
    # mathematics (precalculus / HS geometry)
    "Calculus", "Complex conjugate", "Complex number", "Complex plane",
    "Convergence", "Euclidean distance", "Imaginary part",
    "Initial condition", "Log transform", "Real part",
    "Trigonometric form", "Vertices",
    # probability (AP Statistics)
    "Central limit theorem", "Conditional probability",
    "Cumulative distribution function", "Law of large numbers",
    "Law of total probability", "Normal distribution",
    "Probability density function", "Probability mass function",
    # statistics (AP Statistics)
    "Histogram", "Residuals", "Sample mean", "Sample variance",
    "Scatter plot", "Simple regression model", "Weighted average",
    # calculus (AP Calculus BC / precalculus trig)
    "Angle sum identities", "Taylor series",
    # game-theory (basic)
    "Zero-sum game",
    # microeconomics (AP Micro)
    "Marginal revenue", "Producer surplus",
    # other (meta terms / HS)
    "Exercise", "Industrial Revolution", "Lecture",
}

# === ADVANCED terms: graduate level (PhD courses, research, specialist theory) ===
ADVANCED_TERMS = {
    # dynamic-programming (grad-level functional analysis / control theory)
    "Bellman operator", "Continuation value", "Cost-to-go function",
    # economics (grad macro / micro / trade / public finance)
    "Autarky equilibrium", "Consumption-smoothing model",
    "Cyclical price dynamics", "Distribution dynamics",
    "Dynamic Laffer curve", "Equalizing Difference Model",
    "Exogenous initial capital stock", "Financial repression",
    "First fundamental welfare theorem", "Flow utility function",
    "Forward-looking difference equation", "Geary–Khamis dollar",
    "Input-output model", "Jump variable", "Lake model",
    "Leontief Inverse", "Money-financed government deficit",
    "Multiple consumer economy", "Second fundamental welfare theorem",
    "Seigniorage", "Stochastic productivity",
    "Tax farming", "Tax-smoothing model",
    # finance (grad finance / monetary theory)
    "Arrow securities", "Barrier option", "Fiscal theory of price levels",
    "Inflation-indexed bonds", "Inflation-tax theory", "Knockout barrier",
    "Legal restrictions theory", "Real bills theory", "Risk-neutral pricing",
    "State-contingent claims", "Stochastic volatility",
    "Unpleasant monetarist arithmetic",
    # game-theory (grad game theory)
    "Folk theorem", "Grim trigger strategy",
    # linear-algebra (grad spectral theory / Perron-Frobenius theory)
    "Gershgorin Circle Theorem", "Invariant subspace",
    "Irreducible matrix", "Perron projection", "Perron-Frobenius theorem",
    "Primitive matrix", "Spectral gap", "Spectral radius", "Spectral theory",
    # macroeconomics (grad macro)
    "Aggregate supply of capital", "Multiplier-accelerator model",
    "OLG model", "Overlapping generations model", "Time to build",
    # mathematics (grad network science / analysis)
    "Authority centrality", "Forcing variable", "Hub centrality",
    "Katz centrality", "Neumann Series Lemma",
    "Vector linear difference equations",
    # microeconomics (grad duality theory)
    "Hicksian demand curve",
    # numerical-methods (grad numerical analysis)
    "Method of successive approximations",
    # probability (grad probability theory)
    "Characteristic function", "Convergence in distribution",
    "Heavy-tailed distribution", "Light-tailed distribution",
    "Moment generating function", "Pareto tail", "Tail index",
    # statistics (grad time series / nonparametric)
    "Asymptotic stationarity", "Non-stationary univariate time series",
    "Silverman's rule",
    # stochastic-processes (grad Markov chain theory)
    "Accessible state", "Communicating states", "Ergodicity",
    "Jump Chain Algorithm", "Stochastic linear difference equation",
    # other (specialist data sources)
    "Survey of Consumer Finances",
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
