from pathlib import Path
import re
from app.config import DOCS_DIR, GEMINI_API_KEY, GEMINI_MODEL

def retrieve_policy(query: str, top_k: int=3):
    path=DOCS_DIR/"pricing_policy.md"
    text=path.read_text(encoding="utf-8") if path.exists() else ""
    chunks=[c.strip() for c in re.split(r"\n(?=##? )",text) if c.strip()]
    terms=set(re.findall(r"[a-z0-9]+",query.lower()))
    scored=[]
    for chunk in chunks:
        words=set(re.findall(r"[a-z0-9]+",chunk.lower()))
        scored.append((len(terms & words),chunk))
    return [c for score,c in sorted(scored,key=lambda x:x[0],reverse=True)[:top_k] if score>0] or chunks[:top_k]

def local_explanation(rec: dict, policy_chunks: list[str]) -> str:
    flags=rec.get("approval_flags",[])
    return (f"Recommend ${rec['recommended_price']:.2f} per unit for {rec['quantity']:,} units. "
      f"Estimated gross margin is {rec['gross_margin_pct']:.1f}% and the model estimates a {rec['win_probability_pct']:.1f}% win probability. "
      f"The configured minimum price is ${rec['minimum_price']:.2f}; the recommendation is not below that guardrail. "
      + ("Review: " + " ".join(flags) if flags else "No blocking exception was detected by the demo rules.")
      + " These win probabilities are synthetic-data POC estimates and require validation on real historical quotes.")

def explain_recommendation(rec: dict, query: str="Explain the recommended price") -> dict:
    chunks=retrieve_policy(query + " margin discount approval price")
    local=local_explanation(rec,chunks)
    if not GEMINI_API_KEY:
        return {"explanation":local,"provider":"local_fallback","retrieved_policy":chunks}
    try:
        from google import genai
        client=genai.Client(api_key=GEMINI_API_KEY)
        prompt=f"""You are an explanatory assistant for a packaging distributor's pricing analyst. Explain, do not calculate or change, this recommendation. Numeric rules engine values are authoritative. Never suggest a price below minimum_price. If credit_hold is true or approval_flags exist, clearly mention the needed review. Do not invent facts or promise win probability. State that the ML estimate is trained on synthetic demo data.

Recommendation JSON:
{rec}

Retrieved pricing policy excerpts (reference only):
{chr(10).join(chunks)}

Write a concise explanation for a sales rep with price, margin, tradeoffs, and approval flags."""
        response=client.models.generate_content(model=GEMINI_MODEL,contents=prompt)
        return {"explanation":response.text or local,"provider":"gemini","retrieved_policy":chunks}
    except Exception as e:
        return {"explanation":local,"provider":"local_fallback_after_gemini_error","retrieved_policy":chunks,"warning":f"Gemini unavailable: {type(e).__name__}"}
