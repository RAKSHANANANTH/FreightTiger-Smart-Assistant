"""FreightTiger Engineering Case Study: Conversational Shipping Cost Intelligence Engine.

Author: Rakshan Ananth M
Role: Software Engineering Intern (AI & Data)
"""

import logging
import os
import re
import sys
import pandas as pd

# Configure standard structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("FreightTigerAssistant")


def resolve_file(filename: str) -> str:
  """Resolves file paths across local directories, Google Colab, and standard downloads."""
  candidates = [
      filename,
      os.path.join("/content", filename),
      os.path.join(".", filename),
      os.path.join("..", filename),
      os.path.join(os.path.expanduser("~/Downloads"), filename),
  ]
  for candidate in candidates:
    if os.path.exists(candidate):
      return candidate
  return None


class ShippingCostAssistant:

  def __init__(self, output_path: str = None):
    if output_path is None:
      resolved = resolve_file("output.csv")
      if resolved is None:
        raise FileNotFoundError(
            "Output dataset 'output.csv' not found. Please execute the core"
            " pipeline first."
        )
      self.output_path = resolved
    else:
      self.output_path = output_path

    self.df = pd.read_csv(self.output_path)
    self.df["matched_note_id"] = self.df["matched_note_id"].fillna("")
    self.df["reason"] = self.df["reason"].fillna("")
    self.routes = self.df["route"].unique()

  def answer_query(self, query: str) -> str:
    """Interprets natural language questions, extracts corridor and temporal entities,

    and retrieves deterministic, grounded route findings without hallucination.
    """
    q_clean = query.lower()

    # 1. Match Corridor / Route
    matched_route = None
    for r in self.routes:
      parts = [p.lower().strip() for p in r.split("-")]
      if r.lower() in q_clean:
        matched_route = r
        break
      if len(parts) == 2 and parts[0] in q_clean and parts[1] in q_clean:
        matched_route = r
        break

    # 2. Match Date / Year / Month
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }

    matched_year = next((y for y in ["2024", "2025"] if y in q_clean), None)
    matched_month = None
    for m_name, m_num in months.items():
      if re.search(r"\b" + m_name + r"\b", q_clean):
        matched_month = m_num
        break

    # Filter dataset
    filtered = self.df.copy()
    if matched_route:
      filtered = filtered[filtered["route"] == matched_route]

    if matched_year and matched_month:
      target_prefix = f"{matched_year}-{matched_month}"
      filtered = filtered[filtered["week_of"].str.startswith(target_prefix)]
    elif matched_year:
      filtered = filtered[filtered["week_of"].str.startswith(matched_year)]
    elif matched_month:
      filtered = filtered[filtered["week_of"].str.slice(5, 7) == matched_month]

    if filtered.empty:
      scope = (
          f"corridor '{matched_route}'" if matched_route else "any corridor"
      )
      time_scope = f" during {matched_year or ''} {matched_month or ''}".strip()
      return f"No shipment records identified for {scope}{time_scope}."

    flagged_events = filtered[
        filtered["flagged"].isin(["Yes", "No (justified)"])
    ]
    route_header = matched_route if matched_route else "All Monitored Corridors"

    if flagged_events.empty:
      avg_cost = filtered["cost_per_tonne_km"].astype(float).mean()
      return (
          f"[{route_header}] No rate anomalies detected in this operational"
          " window.\nAverage freight rate: INR"
          f" {avg_cost:.2f} / tonne-km (within expected historical and peer"
          " variance)."
      )

    response_lines = [
        f"[{route_header}] Identified {len(flagged_events)} notable pricing"
        " variance event(s):\n"
    ]

    for _, row in flagged_events.iterrows():
      is_justified = row["flagged"] == "No (justified)"
      status_tag = (
          "JUSTIFIED SURGE" if is_justified else "UNJUSTIFIED SPIKE (FLAGGED)"
      )
      note_citation = (
          f" [Cited Note: {row['matched_note_id']}]"
          if row["matched_note_id"]
          else " [No Grounding Note]"
      )

      response_lines.append(
          f"- Week of {row['week_of']}: INR {row['cost_per_tonne_km']} per"
          " tonne-km\n"
          f"  Variance: {row['vs_own_history']} | {row['vs_similar_routes']}\n"
          f"  Status:   {status_tag}{note_citation}\n"
          f"  Finding:  {row['reason']}\n"
      )

    return "\n".join(response_lines)


def run_assistant():
  print("=" * 78)
  print("FREIGHTTIGER SMART ASSISTANT: SHIPPING COST INTELLIGENCE SYSTEM")
  print("=" * 78)

  try:
    assistant = ShippingCostAssistant()
  except FileNotFoundError as e:
    logger.error("%s", e)
    return

  logger.info("Corridor economic dataset loaded successfully.")
  print(
      "Executing benchmark evaluation queries grounded in historical records:\n"
  )

  demo_queries = [
      "Why did Ahmedabad-Mumbai get pricier in January 2025?",
      "What caused Chennai-Bangalore rates to increase in February and March"
      " 2025?",
      "Why was Delhi-Jaipur flagged in November 2024?",
      "Did Mumbai-Pune have justified rate increases in September 2025?",
      "How were shipping costs on Delhi to Chennai in August 2024?",
  ]

  for idx, q in enumerate(demo_queries, 1):
    print(f"[Query {idx}]: " + repr(q))
    answer = assistant.answer_query(q)
    print(answer)
    print("-" * 78)


if __name__ == "__main__":
  run_assistant()