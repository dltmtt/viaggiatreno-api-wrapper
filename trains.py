#!/usr/bin/env python3

__version__ = "0.1"
__author__ = "Matteo Delton"

import logging
from argparse import ArgumentParser, BooleanOptionalAction
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import inquirer
from prettytable import PrettyTable

from ansicolors import Foreground as F
from ansicolors import Style as S
from viaggiatreno import ViaggiaTrenoAPIWrapper as API


class Train:
    """
    A class to represent a train.

    Attributes:
    -----------
    departure_station : str
        The station from which the train departs.
    train_number : int
        The number assigned to the train.
    departure_date : str
        The date on which the train departs.
    category : str, optional
        The category of the train (default is None).
    number_changes : list, optional
        A list of dictionaries containing the new train number after a change
        (default is None).

    Methods:
    --------
    __str__():
        Returns a string representation of the train, including its category
        and number changes if available.
    __repr__():
        Returns a detailed string representation of the train object for debugging.
    """

    def __init__(self, departure_station, train_number, departure_date):
        self.departure_station = departure_station
        self.train_number = train_number
        self.departure_date = departure_date
        self.category = None
        self.number_changes = []

    def __str__(self):
        numbers = str(self.train_number)
        if self.number_changes:
            numbers += "/"
            numbers += "/".join(c["new_train_number"] for c in self.number_changes)

        if self.category:
            return f"{self.category} {numbers}"
        return f"{numbers}"

    def __repr__(self):
        return f"Train({self.departure_station}, {self.train_number}, {self.departure_date})"


def show_statistics():
    s = API.get_statistics()

    print(
        f"Treni in circolazione da mezzanotte: {s['trains_since_midnight']}\n"
        f"Treni in circolazione ora: {s['trains_running']}\n"
        f"{S.DIM}Ultimo aggiornamento: {s['last_update'].strftime('%T')}{S.NORMAL}"
    )


def choose_station(station):
    stations = API.get_stations_matching_prefix(station)

    if not stations:
        print("Nessuna stazione trovata")
        return None

    if len(stations) == 1:
        return stations[0]["name"], stations[0]["id"]

    guesses = [(s["name"], s["id"]) for s in stations]
    choice = inquirer.list_input(message="Seleziona la stazione", choices=guesses)

    selected_station_name = next(s[0] for s in guesses if s[1] == choice)
    selected_station_id = choice

    return selected_station_name, selected_station_id


def _get_track(actual_track, scheduled_track, probable_track=None):
    if actual_track is not None:
        if scheduled_track is not None:
            if actual_track == scheduled_track:
                return F.blue(actual_track)
            else:
                return F.magenta(actual_track)
        else:
            # I know it's reduntant, but I want to be explicit
            return F.blue(actual_track)

    if probable_track is not None:
        return F.blue(probable_track)

    if scheduled_track is not None:
        return scheduled_track

    return ""


def _get_delay(delay, departed_from_origin, actual_departure_track_known=False):
    if departed_from_origin:
        if delay > 0:
            return F.red(f"{delay:+}")
        if delay < 0:
            return F.green(f"{delay:+}")
        return "In orario"
    if actual_departure_track_known:
        return "In stazione"
    return "Non partito"


# TODO: pass a train object and udpate it
def _process_train(train_data, station_id, is_departure):
    train = Train(
        train_data["origin_id"], train_data["number"], train_data["departure_date"]
    )
    train.category = train_data["category"]
    delay, track, dest_or_origin, time = _get_basic_info(train_data, is_departure)

    progress = API.get_train_progress(
        train_data["origin_id"], train_data["number"], train_data["departure_date"]
    )

    train.number_changes = progress["train_number_changes"] if progress else None

    if not progress:
        approximate_data = [train, dest_or_origin, time.strftime("%H:%M"), delay, track]
        for i, r in enumerate(approximate_data):
            approximate_data[i] = F.yellow(r)
        return approximate_data

    departure, stop, arrival = _get_stops(progress, station_id)

    delay = _get_delay(
        progress["delay"],
        progress["departed_from_origin"],
        departure["actual_departure_track"] is not None,
    )

    if is_departure:
        track = _get_track(
            stop["actual_departure_track"],
            stop["scheduled_departure_track"],
            stop["actual_arrival_track"],
        )
    track = _get_track(stop["actual_arrival_track"], stop["scheduled_arrival_track"])

    arrived = stop["actual_arrival_time"] is not None
    departed = stop["actual_departure_time"] is not None

    precise_data = [train, dest_or_origin, time.strftime("%H:%M"), delay, track]

    if arrived and (departed or arrival["actual_arrival_time"]):
        for i, r in enumerate(precise_data):
            if i == 0:
                continue
            precise_data[i] = S.dim(r)
    elif arrived and not departed:
        for i, r in enumerate(precise_data):
            if i == 0:
                continue
            precise_data[i] = S.bold(r)

    return precise_data


def _get_basic_info(train_data, is_departure):
    delay = _get_delay(train_data["delay"], train_data["departed_from_origin"])
    track = _get_track(train_data["actual_track"], train_data["scheduled_track"])

    if is_departure:
        dest_or_origin = train_data["destination"]
        time = train_data["departure_time"]
    else:
        dest_or_origin = train_data["origin"]
        time = train_data["arrival_time"]

    return delay, track, dest_or_origin, time


def _get_stops(progress, station_id):
    departure = None
    stop = None
    arrival = None

    for s in progress["stops"]:
        if s["stop_type"] == "P":
            departure = s

        if s["station_id"] == station_id:
            stop = s

        if s["stop_type"] == "A":
            arrival = s

    if not departure:
        departure = progress["stops"][0]

    if not arrival:
        arrival = progress["stops"][-1]

    return departure, stop, arrival


def show_departures(station_name, station_id, dt, limit=10):
    print(S.bold(f"Partenze da {station_name}"))

    departures = API.get_departures(station_id, dt, limit)
    if not departures:
        print("Nessun treno in partenza nei prossimi 90 minuti.")
        return

    table = PrettyTable()
    table.field_names = ["Treno", "Destinazione", "Partenza", "Ritardo", "Binario"]

    with ThreadPoolExecutor(max_workers=len(departures)) as executor:
        futures = [
            executor.submit(_process_train, t, station_id, True) for t in departures
        ]

        for future in futures:
            t = future.result()
            table.add_row(t)

    print(table)


def show_arrivals(station_name, station_id, dt, limit):
    print(S.bold(f"Arrivi a {station_name}"))

    arrivals = API.get_arrivals(station_id, dt, limit)
    if not arrivals:
        print("Nessun treno in arrivo nei prossimi 90 minuti.")
        return

    table = PrettyTable()
    table.field_names = ["Treno", "Provenienza", "Arrivo", "Ritardo", "Binario"]

    with ThreadPoolExecutor(max_workers=len(arrivals)) as executor:
        futures = [
            executor.submit(_process_train, t, station_id, False) for t in arrivals
        ]

        for future in futures:
            t = future.result()
            table.add_row(t)

    print(table)


def show_progress(selected_train):
    p = API.get_train_progress(
        selected_train.departure_station,
        selected_train.train_number,
        selected_train.departure_date,
    )

    if not p:
        print(
            "ViaggiaTreno non sta fornendo aggiornamenti in tempo reale per questo treno."
        )
        return

    selected_train.category = p["category"]
    selected_train.number_changes = p["train_number_changes"]

    delay = _get_delay(
        p["delay"],
        p["stops"][0]["actual_departure_time"] is not None,
        p["stops"][0]["actual_departure_track"] is not None,
    )

    print(
        f"Treno {selected_train} · {delay}\n"
        f"{p['departure_time'].strftime('%H:%M')} {p['origin']}\n"
        f"{p['arrival_time'].strftime('%H:%M')} {p['destination']}"
    )

    if p["last_update_station"] and p["last_update_time"]:
        last_update_time = p["last_update_time"].strftime("%H:%M")
        print(
            f"\nUltimo aggiornamento: {last_update_time} a {p['last_update_station']}"
        )

    for s in p["stops"]:
        _print_stop_info(s, p["delay"])


def _print_stop_info(s, delay):
    track = _get_track(
        s["actual_departure_track"] or s["actual_arrival_track"],
        s["scheduled_departure_track"] or s["scheduled_arrival_track"],
    )

    if track:
        print(f"\n{s['station_name']} · {track}")
    else:
        print(f"\n{s['station_name']}")

    if s["stop_type"] in ("A", "F"):
        _print_arrival_info(s, delay)

    if s["stop_type"] in ("P", "F"):
        _print_departure_info(s, delay)


def _print_arrival_info(s, delay):
    if actual_arrival_time := s["actual_arrival_time"]:
        if actual_arrival_time > s["scheduled_arrival_time"]:
            actual_arrival_time = F.red(actual_arrival_time.strftime("%H:%M"))
        else:
            actual_arrival_time = F.green(actual_arrival_time.strftime("%H:%M"))
    arr_str = f"Arr.:\t{s['scheduled_arrival_time'].strftime('%H:%M')}"
    if actual_arrival_time:
        arr_str += f"\t{actual_arrival_time}"
    else:
        if not s["actual_departure_time"]:
            arr_time = s["scheduled_arrival_time"] + timedelta(minutes=delay)
            arr_str += F.yellow(f"\t{arr_time.strftime('%H:%M')}")
    print(arr_str)


def _print_departure_info(s, delay):
    if actual_departure_time := s["actual_departure_time"]:
        if actual_departure_time > s["scheduled_departure_time"] + timedelta(
            seconds=30
        ):
            actual_departure_time = F.red(actual_departure_time.strftime("%H:%M"))
        else:
            actual_departure_time = F.green(actual_departure_time.strftime("%H:%M"))
    dep_str = f"Dep.:\t{s['scheduled_departure_time'].strftime('%H:%M')}"
    if actual_departure_time:
        dep_str += f"\t{actual_departure_time}"
    else:
        if not s["actual_arrival_time"]:
            dep_time = s["scheduled_departure_time"] + timedelta(minutes=delay)
            dep_str += F.yellow(f"\t{dep_time.strftime('%H:%M')}")
    print(dep_str)


if __name__ == "__main__":
    ap = ArgumentParser(description="Get information about trains in Italy")

    ap.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    ap.add_argument(
        "-d",
        "--departures",
        metavar="STATION",
        type=str,
        help="show departures from STATION",
    )
    ap.add_argument(
        "-a",
        "--arrivals",
        metavar="STATION",
        type=str,
        help="show arrivals to STATION",
    )
    ap.add_argument(
        "-n",
        "--train-number",
        metavar="NUMBER",
        type=int,
        help="show progress of train NUMBER",
    )
    ap.add_argument(
        "-s",
        "--solutions",
        metavar=("DEPARTURE", "ARRIVAL"),
        type=str,
        nargs=2,
        help="show journey solutions from DEPARTURE to ARRIVAL",
    )
    ap.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        type=str,
        help="date to use for the other actions (defaults to today)",
    )
    ap.add_argument(
        "--time",
        metavar="HH:MM",
        type=str,
        help="time to use for the other actions (defaults to now)",
    )
    ap.add_argument(
        "--limit",
        metavar="N",
        type=int,
        help="limit the number of results to N (defaults to 10)",
        default=10,
    )
    ap.add_argument(
        "--stats",
        action=BooleanOptionalAction,
        help="show/don't show statistics about trains (defaults to True)",
        default=True,
    )
    ap.add_argument(
        "--log-level",
        metavar="LEVEL",
        type=str,
        help="set the logging level (defaults to WARNING)",
        default="WARNING",
    )

    ap.epilog = (
        "Departures and arrivals show trains from/to the selected "
        "station in a range from 15 minutes before to 90 minutes after "
        "the selected time."
    )

    args = ap.parse_args()

    if args.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        print(
            f"Invalid log level: {F.red(args.log_level)} "
            "(valid values are: DEBUG, INFO, WARNING, ERROR, CRITICAL)."
        )

        exit(1)

    logging.basicConfig(level=args.log_level)

    if args.stats:
        show_statistics()

    if args.date:
        date_ = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        date_ = datetime.now().date()

    if args.time:
        time_ = datetime.strptime(args.time, "%H:%M").time()
    else:
        time_ = datetime.now().time()

    results_limit = args.limit if args.limit else 10

    search_datetime = datetime.combine(date_, time_)

    if args.departures:
        departure_station_name, departure_station_id = choose_station(args.departures)
        show_departures(
            departure_station_name, departure_station_id, search_datetime, results_limit
        )

    if args.arrivals:
        arrival_station_name, arrival_station_id = choose_station(args.arrivals)
        show_arrivals(
            arrival_station_name, arrival_station_id, search_datetime, results_limit
        )

    if args.train_number:
        train_info = API.get_train_info(args.train_number)
        train_to_monitor = Train(
            train_info["departure_station_id"],
            train_info["number"],
            train_info["departure_date"],
        )
        show_progress(train_to_monitor)

    if args.solutions:
        print("Not implemented yet")
