from datetime import date, datetime

from pydantic import BaseModel


class Stats(BaseModel):
    trains_since_midnight: int
    trains_running: int
    last_update: datetime


class BaseStation(BaseModel):
    name: str
    station_id: str


class Departure(BaseModel):
    category: str
    number: int
    departure_date: date
    origin_station_id: str
    destination: str
    scheduled_track: str | None
    actual_track: str | None
    departure_time: datetime
    departed_from_origin: bool
    delay: int
    warning: str | None


class Arrival(BaseModel):
    category: str
    number: int
    departure_date: date
    origin_station_id: str
    origin: str
    scheduled_track: str | None
    actual_track: str | None
    arrival_time: datetime
    departed_from_origin: bool
    delay: int
    warning: str | None


class TrainInfo(BaseModel):
    number: int
    origin_station_id: str
    departure_date: date
    origin: str


class TrainStop(BaseModel):
    station_id: str
    name: str
    stop_type: str
    actual_arrival_time: datetime | None
    actual_departure_time: datetime | None
    arrived: bool
    departed: bool
    scheduled_arrival_time: datetime | None
    scheduled_departure_time: datetime | None
    scheduled_arrival_track: str | None
    actual_arrival_track: str | None
    scheduled_departure_track: str | None
    actual_departure_track: str | None


class TrainProgress(BaseModel):
    last_update_time: datetime | None
    last_update_station: str | None
    train_type: str
    category: str
    number: int
    departure_date: date
    origin_station_id: str
    origin: str
    destination: str
    destination_station_id: str
    train_number_changes: list[dict]
    departure_time: datetime
    arrival_time: datetime
    departed_from_origin: bool
    delay: int
    warning: str
    delay_reason: str | None
    stops: list[TrainStop]