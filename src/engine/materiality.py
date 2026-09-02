import os
import yaml
import numpy as np
import pandas as pd

def load_yaml(path):
    """Loads a YAML file safely."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing configuration file: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_date_column_and_grain(kpi_def):
    """Determines the date column and grain type for a KPI."""
    grain = kpi_def.get("source_grain", "daily")
    if grain == "weekly":
        return "week_start", "weekly"
    elif grain == "monthly":
        return "month", "monthly"
    return "date", "daily"

def get_date_range_span_days(date_series, grain):
    """Calculates total calendar coverage of the dataset in days."""
    if date_series.empty:
        return 0
    
    # Ensure datetime format
    dates = pd.to_datetime(date_series)
    min_date = dates.min()
    
    if grain == "monthly":
        # Span to the end of the maximum month
        max_date = dates.max() + pd.offsets.MonthEnd(0)
    elif grain == "weekly":
        # Span to the end of the 7-day week
        max_date = dates.max() + pd.Timedelta(days=6)
    else:
        max_date = dates.max()
        
    return (max_date - min_date).days + 1

def calculate_kpi_value(df, kpi_name, kpi_def):
    """
    Calculates the aggregated KPI value over the given dataframe
    according to its configured aggregation method and formula.
    Returns the value (AHT in minutes, others as fractions on 0.0-1.0 scale
    or CSAT on 0-100 scale).
    """
    if df.empty:
        return None
        
    agg_method = kpi_def.get("aggregation_method", "weighted_average")
    num_field = kpi_def.get("numerator_field")
    den_field = kpi_def.get("denominator_field")
    
    # 1. Special Case: CSAT
    if kpi_name == "CSAT" and agg_method == "weighted_average":
        # CSAT is naturally on a 0-100 scale.
        # Formula: sum(csat_score * survey_responses) / sum(survey_responses)
        numerator = (df["csat_score"] * df["survey_responses"]).sum()
        denominator = df["survey_responses"].sum()
        if denominator == 0:
            raise ZeroDivisionError("CSAT survey_responses sum is zero.")
        return float(numerator / denominator)
        
    # 2. General Weighted Average / Ratio-based KPIs
    if agg_method == "weighted_average" and num_field in df.columns and den_field in df.columns:
        numerator = df[num_field].sum()
        denominator = df[den_field].sum()
        if denominator == 0:
            raise ZeroDivisionError(f"Zero denominator encountered in ratio calculation for KPI '{kpi_name}'.")
        val = float(numerator / denominator)
        
        # Unit Conversions
        raw_unit = kpi_def.get("raw_unit")
        display_unit = kpi_def.get("display_unit")
        if raw_unit == "seconds" and display_unit == "minutes":
            val /= 60.0  # e.g., AHT seconds to minutes
        # FCR, Repeat Contact, and Retention Rate are kept as fractions (0.0-1.0) internally.
        # This matches their threshold scale (e.g. 0.02, 0.03, 0.005).
        return val

    # 3. Fallback: Simple column average
    val_col = kpi_def.get("value_column")
    col_candidates = [
        val_col,
        kpi_name,
        kpi_name.lower(),
        kpi_name.replace("_", " ").lower(),
        kpi_name.replace(" ", "_").lower(),
        "val",
        "value",
        "score",
        "rate",
        "ai_resolution_rate"
    ]
    col_to_use = None
    for candidate in col_candidates:
        if candidate and candidate in df.columns:
            col_to_use = candidate
            break
            
    if col_to_use is None:
        # Fallback: look for any numeric column not in common date/dimension fields
        ignore_cols = {"date", "date_parsed", "week_start", "month", "region", "product", "customer_segment", "agent_team", "ai_assisted"}
        for col in df.columns:
            if col not in ignore_cols and pd.api.types.is_numeric_dtype(df[col]):
                col_to_use = col
                break
            
    if col_to_use is not None:
        # Check if NaN values exist
        valid_series = df[col_to_use].dropna()
        if valid_series.empty:
            return None
        val = float(valid_series.mean())
        # For AI Resolution Rate in CSV, the values are on 0-100 scale.
        # Convert to 0.0-1.0 scale to be consistent with other percentages if display_unit is percentage.
        if kpi_def.get("display_unit") == "percentage" and val > 1.0:
            val /= 100.0
        return val
        
    raise ValueError(f"Could not calculate KPI '{kpi_name}': required fields/columns not found in data.")

def analyze_kpi_change(kpi_name, kpi_definitions, data_dir, baseline_period, comparison_period):
    """
    Performs deterministic materiality and change detection analysis for a KPI.
    
    Parameters:
      kpi_name: Name of the KPI to analyze (e.g., 'AHT').
      kpi_definitions: Dict containing all KPI YAML definitions.
      data_dir: Path to the directory containing data files.
      baseline_period: Tuple of (start_date, end_date) as strings.
      comparison_period: Tuple of (start_date, end_date) as strings.
      
    Returns:
      A structured dictionary adhering to the StoryProof result schema.
    """
    warnings = []
    
    # 1. Retrieve KPI semantic contract
    kpi_def = kpi_definitions.get(kpi_name)
    if not kpi_def:
        raise ValueError(f"KPI '{kpi_name}' is not defined in KPI definitions.")
        
    source_file = kpi_def.get("source")
    if not source_file:
        raise ValueError(f"Source file not specified for KPI '{kpi_name}'.")
        
    file_path = os.path.join(data_dir, source_file)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Data file '{source_file}' does not exist for KPI '{kpi_name}'.")
        
    # Load dataset
    df = pd.read_csv(file_path)
    
    # Determine date grain
    date_col, grain = get_date_column_and_grain(kpi_def)
    if date_col not in df.columns:
        raise ValueError(f"Date column '{date_col}' missing from data file '{source_file}'.")
        
    # Convert dates to pandas datetime
    df['date_parsed'] = pd.to_datetime(df[date_col])
    
    # Parse period bounds
    b_start, b_end = pd.to_datetime(baseline_period[0]), pd.to_datetime(baseline_period[1])
    c_start, c_end = pd.to_datetime(comparison_period[0]), pd.to_datetime(comparison_period[1])
    
    if b_start > b_end or c_start > c_end:
        raise ValueError(f"Invalid date ranges: start date must be before or equal to end date.")
        
    # Calculate available history in dataset
    available_days = get_date_range_span_days(df['date_parsed'], grain)
    required_days = kpi_def.get("minimum_history_days", 30)
    sufficient_history = available_days >= required_days
    
    # Check history sufficiency
    if not sufficient_history:
        return {
            "kpi_name": kpi_name,
            "status": "INSUFFICIENT_HISTORY",
            "baseline": {
                "start": baseline_period[0],
                "end": baseline_period[1],
                "value": None,
                "observation_count": 0,
                "mean": None,
                "standard_deviation": None
            },
            "comparison": {
                "start": comparison_period[0],
                "end": comparison_period[1],
                "value": None,
                "observation_count": 0
            },
            "change": {
                "absolute": None,
                "relative_percent": None,
                "direction": "NO_MATERIAL_DIRECTION"
            },
            "materiality": {
                "threshold": float(kpi_def.get("materiality_threshold", 0.0)),
                "threshold_type": kpi_def.get("threshold_type", "relative"),
                "crossed": False
            },
            "statistical_signal": {
                "z_score": None,
                "unusual": False,
                "method": "z-score"
            },
            "history": {
                "available_days": int(available_days),
                "required_days": int(required_days),
                "sufficient": False
            },
            "warnings": [f"Insufficient historical data. Available: {available_days} days, Required: {required_days} days."]
        }
        
    # Filter periods
    baseline_df = df[(df['date_parsed'] >= b_start) & (df['date_parsed'] <= b_end)]
    comparison_df = df[(df['date_parsed'] >= c_start) & (df['date_parsed'] <= c_end)]
    
    # Check baseline presence
    if baseline_df.empty:
        raise ValueError(f"No baseline observations found between {baseline_period[0]} and {baseline_period[1]}.")
        
    # Check comparison presence
    if comparison_df.empty:
        return {
            "kpi_name": kpi_name,
            "status": "NOT_MATERIAL",
            "baseline": {
                "start": baseline_period[0],
                "end": baseline_period[1],
                "value": None,
                "observation_count": 0,
                "mean": None,
                "standard_deviation": None
            },
            "comparison": {
                "start": comparison_period[0],
                "end": comparison_period[1],
                "value": None,
                "observation_count": 0
            },
            "change": {
                "absolute": None,
                "relative_percent": None,
                "direction": "NO_MATERIAL_DIRECTION"
            },
            "materiality": {
                "threshold": float(kpi_def.get("materiality_threshold", 0.0)),
                "threshold_type": kpi_def.get("threshold_type", "relative"),
                "crossed": False
            },
            "statistical_signal": {
                "z_score": None,
                "unusual": False,
                "method": "z-score"
            },
            "history": {
                "available_days": int(available_days),
                "required_days": int(required_days),
                "sufficient": True
            },
            "warnings": [f"Comparison period is empty. No observations found between {comparison_period[0]} and {comparison_period[1]}."]
        }
        
    # 2. Construct baseline time series at natural grain
    # Group by date column and compute KPI value for each time interval
    try:
        baseline_grouped = baseline_df.groupby(date_col)
        baseline_ts = []
        for name_val, group in baseline_grouped:
            kpi_val = calculate_kpi_value(group, kpi_name, kpi_def)
            if kpi_val is not None:
                baseline_ts.append(kpi_val)
                
        if not baseline_ts:
            raise ValueError(f"Failed to calculate time series values for baseline period.")
            
        baseline_ts = pd.Series(baseline_ts)
        baseline_mean = float(baseline_ts.mean())
        baseline_std = float(baseline_ts.std()) if len(baseline_ts) > 1 else 0.0
        baseline_obs_count = len(baseline_ts)
    except Exception as e:
        raise ValueError(f"Error constructing baseline time-series metrics: {e}")
        
    # 3. Calculate baseline and comparison overall period values
    try:
        baseline_value = calculate_kpi_value(baseline_df, kpi_name, kpi_def)
        comparison_value = calculate_kpi_value(comparison_df, kpi_name, kpi_def)
        comparison_obs_count = len(comparison_df.groupby(date_col))
    except ZeroDivisionError as e:
        # Denominator is zero
        raise ValueError(f"Calculation failed due to zero denominator: {e}")
        
    if baseline_value is None or comparison_value is None:
        raise ValueError(f"Calculated period values are null.")
        
    # 4. Calculate change metrics
    absolute_change = comparison_value - baseline_value
    
    if baseline_value != 0:
        relative_change = absolute_change / baseline_value
    else:
        relative_change = 0.0
        warnings.append("Baseline value is zero; relative change defaulted to 0.0.")
        
    # 5. Check business materiality
    threshold = float(kpi_def.get("materiality_threshold", 0.0))
    threshold_type = kpi_def.get("threshold_type", "relative")
    
    if threshold_type == "relative":
        crossed = abs(relative_change) >= threshold
    elif threshold_type == "absolute_percentage_points":
        crossed = abs(absolute_change) >= threshold
    else:
        raise ValueError(f"Unsupported threshold type '{threshold_type}' configured for KPI '{kpi_name}'.")
        
    # Direction
    if crossed:
        direction = "INCREASE" if absolute_change > 0 else "DECREASE"
        status = "MATERIAL"
    else:
        direction = "NO_MATERIAL_DIRECTION"
        status = "NOT_MATERIAL"
        
    # 6. Calculate statistical signal
    z_score = None
    unusual = False
    
    if baseline_std > 0:
        z_score = (comparison_value - baseline_mean) / baseline_std
        # Standard threshold: z-score magnitude >= 2.0 (representing 2 standard deviations)
        if abs(z_score) >= 2.0:
            unusual = True
    else:
        warnings.append("Baseline standard deviation is zero; z-score cannot be computed.")
        
    return {
        "kpi_name": kpi_name,
        "status": status,
        "baseline": {
            "start": baseline_period[0],
            "end": baseline_period[1],
            "value": float(baseline_value),
            "observation_count": int(baseline_obs_count),
            "mean": float(baseline_mean),
            "standard_deviation": float(baseline_std)
        },
        "comparison": {
            "start": comparison_period[0],
            "end": comparison_period[1],
            "value": float(comparison_value),
            "observation_count": int(comparison_obs_count)
        },
        "change": {
            "absolute": float(absolute_change),
            "relative_percent": float(relative_change * 100.0),
            "direction": direction
        },
        "materiality": {
            "threshold": threshold,
            "threshold_type": threshold_type,
            "crossed": bool(crossed)
        },
        "statistical_signal": {
            "z_score": float(z_score) if z_score is not None else None,
            "unusual": bool(unusual),
            "method": "z-score"
        },
        "history": {
            "available_days": int(available_days),
            "required_days": int(required_days),
            "sufficient": True
        },
        "warnings": warnings
    }
