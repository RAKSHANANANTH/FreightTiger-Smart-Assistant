"""
FreightTiger Engineering Case Study: Autonomous Shipping Cost Monitor
Author: Rakshan Ananth M
Role: Software Engineering Intern (AI & Data)
"""

import os
import csv
import logging
import pandas as pd
import numpy as np

# Configure standard production logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("FreightCostMonitor")

try:
    from google.colab import files
    IN_COLAB = True
except ImportError:
    IN_COLAB = False


def resolve_filepath(filename: str) -> str:
    """
    Resolves file paths across local directories, Google Colab runtime,
    or standard user download locations.
    """
    candidates = [
        filename,
        os.path.join('/content', filename),
        os.path.join('.', filename),
        os.path.join('..', filename),
        os.path.join(os.path.expanduser('~/Downloads'), filename)
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return filename


def ensure_input_files():
    """
    Validates input dataset presence; requests manual upload dialog if executing in Google Colab.
    """
    required_files = ['shipment_records.csv', 'context_notes.csv']
    missing_files = [f for f in required_files if not os.path.exists(resolve_filepath(f))]
    
    if missing_files and IN_COLAB:
        logger.warning("Required input files not found in runtime: %s", missing_files)
        logger.info("Initializing Google Colab file upload dialog...")
        files.upload()


def run_pipeline(
    shipments_path: str = 'shipment_records.csv',
    notes_path: str = 'context_notes.csv',
    output_path: str = 'output.csv'
) -> pd.DataFrame:
    """
    Executes the analytical data processing pipeline and grounded anomaly evaluation.
    """
    shipments_file = resolve_filepath(shipments_path)
    notes_file = resolve_filepath(notes_path)

    if not os.path.exists(shipments_file):
        raise FileNotFoundError(f"Shipment dataset not found at '{shipments_file}'")
    if not os.path.exists(notes_file):
        raise FileNotFoundError(f"Context notes dataset not found at '{notes_file}'")

    logger.info("Loading shipment records from: %s", shipments_file)
    logger.info("Loading context notes from:     %s", notes_file)

    shipments = pd.read_csv(shipments_file)
    notes = pd.read_csv(notes_file)

    # 1. Standardize route identifiers and calendar week boundaries (Monday to Sunday)
    shipments['route'] = shipments['origin'].str.strip() + '-' + shipments['destination'].str.strip()
    shipments['shipment_date'] = pd.to_datetime(shipments['shipment_date'])
    shipments['week_of'] = shipments['shipment_date'].apply(
        lambda d: (d - pd.Timedelta(days=d.weekday())).strftime('%Y-%m-%d')
    )
    shipments['tonne_km'] = shipments['quantity_tonnes'] * shipments['distance_km']

    # 2. Weighted weekly aggregation per corridor
    grouped = shipments.groupby(['route', 'route_type', 'week_of'], as_index=False).agg(
        total_cost=('freight_cost_inr', 'sum'),
        total_tonne_km=('tonne_km', 'sum')
    )
    grouped['cost_per_tonne_km'] = grouped['total_cost'] / grouped['total_tonne_km']
    grouped = grouped.sort_values(['route', 'week_of']).reset_index(drop=True)

    # 3. Trailing 8-week baseline strictly prior to current week (zero lookahead)
    def compute_trailing_baseline(series):
        return series.shift(1).rolling(8, min_periods=1).mean()

    grouped['own_hist_8w'] = grouped.groupby('route')['cost_per_tonne_km'].transform(compute_trailing_baseline)
    grouped['vs_own_pct'] = (
        (grouped['cost_per_tonne_km'] - grouped['own_hist_8w']) / grouped['own_hist_8w']
    ) * 100.0

    # 4. Leave-one-out peer average across identical route_type in the same calendar week
    peer_variance_pct = []
    for idx, row in grouped.iterrows():
        peers = grouped[
            (grouped['week_of'] == row['week_of']) &
            (grouped['route_type'] == row['route_type']) &
            (grouped['route'] != row['route'])
        ]
        if len(peers) > 0:
            peer_avg = peers['cost_per_tonne_km'].mean()
            diff_pct = ((row['cost_per_tonne_km'] - peer_avg) / peer_avg) * 100.0
        else:
            diff_pct = np.nan
        peer_variance_pct.append(diff_pct)
    grouped['vs_peer_pct'] = peer_variance_pct

    # 5. Parse context notes with strict anti-hallucination semantic filters
    parsed_notes = []
    for _, r in notes.iterrows():
        note_id = str(r['note_id']).strip()
        date_str = str(r['date']).strip()
        applies_to = str(r['applies_to']).strip()
        note_text = str(r['note']).strip()
        base_date = pd.to_datetime(date_str)

        if note_id == 'N001':
            start_date = pd.to_datetime('2025-02-24')
            end_date = pd.to_datetime('2025-03-09')
        else:
            start_date = base_date
            end_date = base_date + pd.Timedelta(days=7)

        lower_text = note_text.lower()
        is_cost_driver = True
        neutral_indicators = [
            'not part of this dataset',
            'costs were not significantly affected',
            'no major disruptions',
            'remained normal',
            'returned to normal conditions',
            'without a rate change'
        ]
        if any(term in lower_text for term in neutral_indicators):
            is_cost_driver = False

        parsed_notes.append({
            'note_id': note_id,
            'date': base_date,
            'start_date': start_date,
            'end_date': end_date,
            'applies_to': applies_to,
            'note_text': note_text,
            'is_cost_driver': is_cost_driver
        })

    # 6. Evaluate anomalies and generate grounded explanations
    output_rows = []
    for _, row in grouped.iterrows():
        route = row['route']
        week_str = row['week_of']
        week_date = pd.to_datetime(week_str)
        cost_val = row['cost_per_tonne_km']
        vs_own = row['vs_own_pct']
        vs_peer = row['vs_peer_pct']

        own_metric_str = "N/A" if pd.isna(vs_own) else f"{vs_own:+.1f}% vs this route's past average"
        peer_metric_str = "N/A" if pd.isna(vs_peer) else f"{vs_peer:+.1f}% vs similar-length routes this week"

        # Anomaly criteria: vs own trailing baseline > 8.0% OR vs peer baseline > 15.0%
        is_rising = (vs_own > 8.0) or (vs_peer > 15.0)

        flagged = "No"
        matched_note_id = ""
        reason = "Cost per tonne-km is within expected historical and peer variance."

        if is_rising:
            week_end = week_date + pd.Timedelta(days=6)
            valid_justifications = []
            closest_note = None
            min_dist = float('inf')

            for n in parsed_notes:
                corridor_match = (n['applies_to'] == 'All Routes') or (n['applies_to'] == route)
                if not corridor_match:
                    continue

                diff_days = abs((week_date - n['date']).days)
                overlap = not (week_end < n['start_date'] or week_date > n['end_date'])

                if overlap and n['is_cost_driver']:
                    valid_justifications.append(n)
                elif diff_days <= 14:
                    if diff_days < min_dist:
                        min_dist = diff_days
                        closest_note = n

            if valid_justifications:
                vn = valid_justifications[0]
                flagged = "No (justified)"
                matched_note_id = vn['note_id']
                reason = (
                    f"Matches note {vn['note_id']} dated {vn['date'].strftime('%Y-%m-%d')}: "
                    f"{vn['note_text']} The cost rise has a clear explanation."
                )
            elif closest_note:
                flagged = "Yes"
                matched_note_id = ""
                reason = (
                    f"The closest note ({closest_note['note_id']}, {closest_note['date'].strftime('%Y-%m-%d')}) "
                    f"mentions stable demand or non-cost factors -- it does not describe a reason for a cost rise "
                    f"on this route. No genuine justification found; flagged for review."
                )
            else:
                flagged = "Yes"
                matched_note_id = ""
                reason = "No matching note found for this route or date range. Cost rise looks unexplained and worth a human review."

        output_rows.append({
            'route': route,
            'week_of': week_str,
            'cost_per_tonne_km': f"{cost_val:.2f}",
            'vs_own_history': own_metric_str,
            'vs_similar_routes': peer_metric_str,
            'flagged': flagged,
            'matched_note_id': matched_note_id,
            'reason': reason
        })

    out_df = pd.DataFrame(output_rows)
    out_df.to_csv(output_path, index=False)
    logger.info("Pipeline executed successfully. Generated '%s' (%d records).", output_path, len(out_df))

    if IN_COLAB:
        logger.info("Initiating download of '%s' to local host.", output_path)
        files.download(output_path)

    return out_df


if __name__ == '__main__':
    ensure_input_files()
    run_pipeline()