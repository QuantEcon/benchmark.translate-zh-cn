"""Add hand-crafted context sentences for terms missing lecture context.

These 36 terms don't appear (even fuzzy) in QuantEcon lecture prose at
the single-paragraph level.  Rather than leave them without context,
we provide one curated usage sentence each, flagged with
source="curated-context" so the provenance is clear.

Run: uv run python scripts/add_missing_contexts.py
"""

import json
from pathlib import Path

DATA_DIR = Path("data/terms")

# {english_term: context_sentence}
CURATED_CONTEXTS: dict[str, str] = {
    # dynamic-programming
    "Stable cycle": "A stable cycle is a periodic orbit to which nearby trajectories converge over time.",
    # economics
    "Autarky equilibrium": "In autarky equilibrium, a closed economy determines prices and quantities without international trade.",
    "Corporate tax rate": "The corporate tax rate is the percentage of a firm's profits collected as tax by the government.",
    "Forward-looking difference equation": "A forward-looking difference equation relates the current value of a variable to its expected future values.",
    "Geary–Khamis dollar": "The Geary–Khamis dollar is a hypothetical unit of currency used for purchasing power parity comparisons across countries.",
    "Jump variable": "A jump variable can change discontinuously at the initial date to satisfy forward-looking equilibrium conditions.",
    "Multiple consumer economy": "In a multiple consumer economy, heterogeneous agents with different preferences interact through markets.",
    "Perfect foresight model": "A perfect foresight model assumes all agents correctly anticipate future prices and quantities.",
    "Projected corporate tax revenue": "Projected corporate tax revenue is the government's forecast of income from corporate taxation.",
    "Reform and liberalization": "Reform and liberalization refer to policy changes that reduce government intervention in markets.",
    "Second fundamental welfare theorem": "The second fundamental welfare theorem states that any Pareto efficient allocation can be achieved as a competitive equilibrium with appropriate redistribution.",
    "Tax farming": "Tax farming is a system where the right to collect taxes is auctioned to private bidders.",
    "Welfare maximization problem": "The welfare maximization problem seeks allocations that maximize a social welfare function subject to resource constraints.",
    # finance
    "Barrier option": "A barrier option is an exotic option whose payoff depends on whether the underlying asset reaches a specified price level.",
    "Inflation-tax theory": "Inflation-tax theory analyzes how governments can finance expenditures by expanding the money supply, effectively taxing holders of money.",
    "Knockout barrier": "A knockout barrier is a price level at which a barrier option ceases to exist.",
    "Real bills theory": "The real bills theory holds that money issued against short-term commercial paper will not be inflationary.",
    "Stochastic volatility": "Stochastic volatility models allow the variance of asset returns to follow its own random process.",
    # game-theory
    "Folk theorem": "The folk theorem establishes that in infinitely repeated games, any feasible and individually rational payoff can be sustained as an equilibrium.",
    "Grim trigger strategy": "A grim trigger strategy permanently punishes any defection by reverting to the worst equilibrium forever.",
    # macroeconomics
    "Aggregate supply of capital": "The aggregate supply of capital is the total amount of physical capital available in an economy for production.",
    # mathematics
    "Vector linear difference equations": "Vector linear difference equations describe the evolution of a system of variables through matrix recursions.",
    # microeconomics
    "Hicksian demand curve": "The Hicksian demand curve shows how quantity demanded varies with price while holding utility constant.",
    "Marginal revenue": "Marginal revenue is the additional income earned from selling one more unit of output.",
    "Marshallian demand curve": "The Marshallian demand curve relates quantity demanded to price while holding income constant.",
    "Non-satiation": "Non-satiation is the assumption that consumers always prefer more of a good to less.",
    # numerical-methods
    "Method of successive approximations": "The method of successive approximations iteratively refines an initial guess until convergence to a fixed point.",
    "Path simulation": "Path simulation generates sample trajectories of a stochastic process using random number draws.",
    # other
    "Federal Reserve Economic Data": "Federal Reserve Economic Data (FRED) is an online database of economic time series maintained by the Federal Reserve Bank of St. Louis.",
    "National Bureau of Economic Research": "The National Bureau of Economic Research (NBER) is a private nonprofit organization that conducts and disseminates economic research.",
    # statistics
    "Forecast errors": "Forecast errors are the differences between predicted and actual values of a time series.",
    "Gaussian kernel": "A Gaussian kernel is a weighting function based on the normal distribution, commonly used in kernel density estimation.",
    "Silverman's rule": "Silverman's rule is a method for selecting the bandwidth in kernel density estimation based on the sample size and standard deviation.",
    # stochastic-processes
    "Accessible state": "An accessible state is one that can be reached with positive probability from a given starting state in a Markov chain.",
    "Communicating states": "Two states in a Markov chain are communicating if each is accessible from the other.",
    "Jump Chain Algorithm": "The Jump Chain Algorithm constructs a discrete-time chain from a continuous-time Markov process by recording only state transitions.",
}


def main():
    updated_files = set()
    terms_enriched = 0

    for filepath in sorted(DATA_DIR.glob("_seed_*.json")):
        data = json.loads(filepath.read_text(encoding="utf-8"))
        changed = False

        for term in data:
            en = term["en"]
            if en in CURATED_CONTEXTS and not term.get("contexts"):
                term["contexts"] = [
                    {"text": CURATED_CONTEXTS[en], "source": "curated-context"}
                ]
                changed = True
                terms_enriched += 1
                print(f"  ✓ {en}")

        if changed:
            filepath.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            updated_files.add(filepath.name)

    print(f"\nEnriched {terms_enriched} terms across {len(updated_files)} files")

    # Verify no terms remain without context
    remaining = 0
    for filepath in sorted(DATA_DIR.glob("_seed_*.json")):
        data = json.loads(filepath.read_text(encoding="utf-8"))
        for term in data:
            if not term.get("contexts"):
                remaining += 1
                print(f"  ✗ Still missing: {term['en']}")

    if remaining == 0:
        print("✓ 100% context coverage achieved!")
    else:
        print(f"✗ {remaining} terms still missing context")


if __name__ == "__main__":
    main()
