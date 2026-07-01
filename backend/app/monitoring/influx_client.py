"""Kho số liệu time-series (InfluxDB) - mục 3.2.2, 3.5.

Metrics (CPU, băng thông, tỉ lệ rớt gói...) được lưu ở InfluxDB thay vì
cơ sở dữ liệu quan hệ, tối ưu cho truy vấn theo thời gian.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from influxdb_client import Point, WritePrecision
from influxdb_client.client.influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from app.core.config import get_settings

MEASUREMENT = "device_metrics"


class InfluxMetricsStore:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._client = InfluxDBClient(url=settings.influxdb_url, token=settings.influxdb_token, org=settings.influxdb_org)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._query_api = self._client.query_api()

    def write_metric(self, device_id: str, fields: dict[str, float], timestamp: datetime | None = None) -> None:
        point = Point(MEASUREMENT).tag("device_id", device_id)
        for key, value in fields.items():
            point = point.field(key, float(value))
        if timestamp:
            point = point.time(timestamp, WritePrecision.NS)
        self._write_api.write(bucket=self._settings.influxdb_bucket, record=point)

    def query_metrics(self, device_id: str, time_range: str = "-15m") -> list[dict[str, Any]]:
        flux = f'''
        from(bucket: "{self._settings.influxdb_bucket}")
          |> range(start: {time_range})
          |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
          |> filter(fn: (r) => r.device_id == "{device_id}")
        '''
        tables = self._query_api.query(flux, org=self._settings.influxdb_org)
        records = []
        for table in tables:
            for record in table.records:
                records.append(
                    {
                        "time": record.get_time().isoformat(),
                        "field": record.get_field(),
                        "value": record.get_value(),
                    }
                )
        return records

    def close(self) -> None:
        self._client.close()
