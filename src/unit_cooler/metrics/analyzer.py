"""
New metrics analysis for outdoor unit cooler system.

Provides:
- 時間別の cooling_mode, DUTY比, バルブ操作回数の箱ヒゲ図
- 時系列推移グラフ
- 環境要因との相関分析 (散布図と相関係数)
"""

import datetime
import logging
import zoneinfo

# 分析ライブラリ
try:
    import pandas as pd
    from scipy import stats

    _ANALYSIS_AVAILABLE = True
except ImportError:
    _ANALYSIS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Analysis libraries not available. Install numpy, pandas, scipy for analytics.")

from .collector import MetricsCollector, get_metrics_collector

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")
logger = logging.getLogger(__name__)


class MetricsAnalyzer:
    """Metrics analysis focused on cooling mode and environmental correlations."""

    def __init__(self, collector: MetricsCollector | None = None):
        """Initialize analyzer with metrics collector."""
        self.collector = collector or get_metrics_collector()

    def get_hourly_boxplot_data(self, days: int = 7) -> dict:
        """Get hourly box plot data for cooling_mode, duty_ratio, valve_operations."""
        if not _ANALYSIS_AVAILABLE:
            return {"error": "Analysis libraries not available"}

        end_time = datetime.datetime.now(TIMEZONE)
        start_time = end_time - datetime.timedelta(days=days)

        # Get minute data for cooling_mode and duty_ratio
        minute_data = self.collector.get_minute_data(start_time, end_time, limit=10080)  # 7 days
        # Get hourly data for valve operations
        hourly_data = self.collector.get_hourly_data(start_time, end_time, limit=168)  # 7 days

        # Process minute data
        df_minute = pd.DataFrame(minute_data)
        if not df_minute.empty:
            df_minute["timestamp"] = pd.to_datetime(df_minute["timestamp"])
            df_minute["hour"] = df_minute["timestamp"].dt.hour

        # Process hourly data
        df_hourly = pd.DataFrame(hourly_data)
        if not df_hourly.empty:
            df_hourly["timestamp"] = pd.to_datetime(df_hourly["timestamp"])
            df_hourly["hour"] = df_hourly["timestamp"].dt.hour

        return {
            "cooling_mode_boxplot": self._calculate_hourly_boxplot(df_minute, "cooling_mode"),
            "duty_ratio_boxplot": self._calculate_hourly_boxplot(df_minute, "duty_ratio"),
            "valve_operations_boxplot": self._calculate_hourly_boxplot(df_hourly, "valve_operations"),
        }

    def get_timeseries_data(self, days: int = 7) -> dict:
        """Get time series data for trending analysis."""
        end_time = datetime.datetime.now(TIMEZONE)
        start_time = end_time - datetime.timedelta(days=days)

        minute_data = self.collector.get_minute_data(start_time, end_time, limit=10080)
        hourly_data = self.collector.get_hourly_data(start_time, end_time, limit=168)

        return {
            "cooling_mode_timeseries": [
                {"timestamp": row["timestamp"], "value": row["cooling_mode"]}
                for row in minute_data
                if row["cooling_mode"] is not None
            ],
            "duty_ratio_timeseries": [
                {"timestamp": row["timestamp"], "value": row["duty_ratio"]}
                for row in minute_data
                if row["duty_ratio"] is not None
            ],
            "valve_operations_timeseries": [
                {"timestamp": row["timestamp"], "value": row["valve_operations"]} for row in hourly_data
            ],
        }

    def get_correlation_analysis(self, days: int = 30) -> dict:
        """Get correlation analysis between environmental factors and system metrics."""
        if not _ANALYSIS_AVAILABLE:
            return {"error": "Analysis libraries not available"}

        end_time = datetime.datetime.now(TIMEZONE)
        start_time = end_time - datetime.timedelta(days=days)

        minute_data = self.collector.get_minute_data(start_time, end_time, limit=43200)  # 30 days
        df = pd.DataFrame(minute_data)

        if df.empty:
            return {"error": "No data available for correlation analysis"}

        # Environmental factors
        env_factors = ["temperature", "humidity", "lux", "solar_radiation", "rain_amount"]
        target_metrics = ["cooling_mode", "duty_ratio"]

        correlations = {}
        scatter_data = {}

        for target in target_metrics:
            correlations[target] = {}
            scatter_data[target] = {}

            for factor in env_factors:
                # Filter data where both values are not null
                valid_data = df.dropna(subset=[target, factor])

                if len(valid_data) > 10:  # Minimum data points for correlation
                    corr_coef, p_value = stats.pearsonr(valid_data[factor], valid_data[target])

                    correlations[target][factor] = {
                        "correlation": float(corr_coef),
                        "p_value": float(p_value),
                        "significant": p_value < 0.05,
                        "sample_size": len(valid_data),
                    }

                    # Scatter plot data (sample for performance)
                    if len(valid_data) > 1000:
                        sampled_data = valid_data.sample(n=1000, random_state=42)
                    else:
                        sampled_data = valid_data

                    scatter_data[target][factor] = [
                        {"x": float(row[factor]), "y": float(row[target])}
                        for _, row in sampled_data.iterrows()
                    ]
                else:
                    correlations[target][factor] = {
                        "correlation": None,
                        "p_value": None,
                        "significant": False,
                        "sample_size": len(valid_data),
                    }
                    scatter_data[target][factor] = []

        return {"correlations": correlations, "scatter_data": scatter_data}

    def _calculate_hourly_boxplot(self, df, column: str) -> list[dict]:
        """Calculate box plot statistics for each hour."""
        if df.empty or column not in df.columns:
            return []

        # Remove null values
        df_clean = df.dropna(subset=[column])
        if df_clean.empty:
            return []

        boxplot_data = []

        for hour in range(24):
            hour_data = df_clean[df_clean["hour"] == hour][column]

            if len(hour_data) > 0:
                stats_data = {
                    "hour": hour,
                    "min": float(hour_data.min()),
                    "q1": float(hour_data.quantile(0.25)),
                    "median": float(hour_data.median()),
                    "q3": float(hour_data.quantile(0.75)),
                    "max": float(hour_data.max()),
                    "count": len(hour_data),
                    "outliers": self._detect_outliers(hour_data),
                }
                boxplot_data.append(stats_data)
            else:
                boxplot_data.append(
                    {
                        "hour": hour,
                        "min": None,
                        "q1": None,
                        "median": None,
                        "q3": None,
                        "max": None,
                        "count": 0,
                        "outliers": [],
                    }
                )

        return boxplot_data

    def _detect_outliers(self, data) -> list[float]:
        """Detect outliers using IQR method."""
        q1 = data.quantile(0.25)
        q3 = data.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outliers = data[(data < lower_bound) | (data > upper_bound)]
        return [float(x) for x in outliers.tolist()]

    def get_summary_statistics(self, days: int = 7) -> dict:
        """Get summary statistics for the dashboard."""
        end_time = datetime.datetime.now(TIMEZONE)
        start_time = end_time - datetime.timedelta(days=days)

        minute_data = self.collector.get_minute_data(start_time, end_time, limit=10080)
        hourly_data = self.collector.get_hourly_data(start_time, end_time, limit=168)
        error_data = self.collector.get_error_data(start_time, end_time, limit=1000)

        # Calculate statistics
        df_minute = pd.DataFrame(minute_data)
        df_hourly = pd.DataFrame(hourly_data)

        return {
            "period_days": days,
            "total_data_points": len(minute_data),
            "total_errors": len(error_data),
            "cooling_mode": self._get_column_stats(df_minute, "cooling_mode"),
            "duty_ratio": self._get_column_stats(df_minute, "duty_ratio"),
            "valve_operations": self._get_column_stats(df_hourly, "valve_operations"),
            "environmental": {
                "temperature": self._get_column_stats(df_minute, "temperature"),
                "humidity": self._get_column_stats(df_minute, "humidity"),
                "lux": self._get_column_stats(df_minute, "lux"),
                "solar_radiation": self._get_column_stats(df_minute, "solar_radiation"),
                "rain_amount": self._get_column_stats(df_minute, "rain_amount"),
            },
        }

    def _get_column_stats(self, df, column: str) -> dict:
        """Get basic statistics for a column."""
        if df.empty or column not in df.columns:
            return {"count": 0, "mean": None, "median": None, "std": None, "min": None, "max": None}

        data = df[column].dropna()
        if len(data) == 0:
            return {"count": 0, "mean": None, "median": None, "std": None, "min": None, "max": None}

        return {
            "count": len(data),
            "mean": float(data.mean()),
            "median": float(data.median()),
            "std": float(data.std()),
            "min": float(data.min()),
            "max": float(data.max()),
        }


def get_metrics_analyzer() -> MetricsAnalyzer:
    """Get metrics analyzer instance."""
    return MetricsAnalyzer()
