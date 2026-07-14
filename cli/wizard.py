from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WizardOptions:
    mode: str
    codes: str
    top: int
    depth: str
    risk: str
    use_llm: bool


def prompt_options() -> WizardOptions:
    try:
        from InquirerPy import inquirer

        mode = inquirer.select(
            message="Select analysis mode:",
            choices=["single", "watchlist", "hot"],
            default="single",
        ).execute()
        codes = ""
        top = 5
        if mode == "single":
            codes = inquirer.text(message="Stock code:", default="600519").execute()
        elif mode == "watchlist":
            codes = inquirer.text(message="Comma-separated stock codes:", default="600519,000858,300750").execute()
            top = int(inquirer.number(message="Analyze top N from watchlist:", default=3).execute())
        else:
            top = int(inquirer.number(message="Analyze top N hot stocks:", default=5).execute())
        depth = inquirer.select(message="Depth:", choices=["quick", "standard", "full"], default="standard").execute()
        risk = inquirer.select(
            message="Risk profile:",
            choices=["conservative", "balanced", "aggressive"],
            default="balanced",
        ).execute()
        use_llm = inquirer.confirm(message="Use LLM compression if OPENAI_API_KEY exists?", default=True).execute()
        return WizardOptions(mode=mode, codes=codes, top=top, depth=depth, risk=risk, use_llm=use_llm)
    except Exception:
        mode = input("Mode [single/watchlist/hot] (single): ").strip() or "single"
        codes = ""
        top = 5
        if mode == "single":
            codes = input("Stock code (600519): ").strip() or "600519"
        elif mode == "watchlist":
            codes = input("Comma-separated stock codes (600519,000858,300750): ").strip() or "600519,000858,300750"
            top = int(input("Analyze top N (3): ").strip() or "3")
        else:
            top = int(input("Analyze top N hot stocks (5): ").strip() or "5")
        depth = input("Depth [quick/standard/full] (standard): ").strip() or "standard"
        risk = input("Risk [conservative/balanced/aggressive] (balanced): ").strip() or "balanced"
        use_llm = (input("Use LLM compression? [Y/n]: ").strip().lower() or "y") != "n"
        return WizardOptions(mode=mode, codes=codes, top=top, depth=depth, risk=risk, use_llm=use_llm)
