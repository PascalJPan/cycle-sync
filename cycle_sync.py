#!/usr/bin/env python3
"""Menstrual cycle phase sync for Google Calendar."""

import argparse
import json
import os
import sys
import math
from datetime import date, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(SCRIPT_DIR, "credentials.json")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
HISTORY_PATH = os.path.join(SCRIPT_DIR, "history.json")

PHASE_COLORS = {
    "Period": "11",       # Tomato/Red
    "Follicular": "2",    # Sage/Green
    "Ovulation": "3",     # Grape/Purple
    "Luteal": "5",        # Banana/Yellow
}

CALENDAR_NAME = "Cycle Phases"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_history():
    """Load period start date history."""
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            data = json.load(f)
        return sorted(set(data.get("period_starts", [])))
    return []


def save_history(starts):
    """Save period start date history."""
    with open(HISTORY_PATH, "w") as f:
        json.dump({"period_starts": sorted(set(starts))}, f, indent=2)


def calculate_cycle_lengths(starts):
    """Calculate cycle lengths from sorted start date strings."""
    dates = [date.fromisoformat(s) for s in starts]
    return [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]


def get_median_cycle_length(starts, default):
    """Return median cycle length from history, or default if insufficient data."""
    lengths = calculate_cycle_lengths(starts)
    if not lengths:
        return default
    sorted_lengths = sorted(lengths)
    n = len(sorted_lengths)
    mid = n // 2
    if n % 2 == 1:
        return sorted_lengths[mid]
    return math.ceil((sorted_lengths[mid - 1] + sorted_lengths[mid]) / 2)


def authenticate():
    """Run the OAuth flow and save the token."""
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"Error: {CREDENTIALS_PATH} not found.")
        print("Download OAuth credentials from Google Cloud Console first.")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print("Authentication successful. Token saved.")


def get_calendar_service():
    """Return an authorized Google Calendar API service."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError(
                "Not authenticated — delete token.json and relaunch to re-authenticate."
            )

    return build("calendar", "v3", credentials=creds)


def get_or_create_cycle_calendar(service):
    """Find or create a dedicated 'Cycle Phases' sub-calendar."""
    calendars = service.calendarList().list().execute()
    for cal in calendars.get("items", []):
        if cal["summary"] == CALENDAR_NAME:
            return cal["id"]

    body = {"summary": CALENDAR_NAME}
    new_cal = service.calendars().insert(body=body).execute()
    print(f"Created new calendar: {CALENDAR_NAME}")
    return new_cal["id"]


def calculate_phases(start_date, cycle_length, period_length, months_ahead):
    """Calculate cycle phases for months_ahead months from start_date."""
    end_limit = start_date + timedelta(days=months_ahead * 31)
    phases = []
    cycle_start = start_date

    while cycle_start < end_limit:
        ovulation_day = cycle_length // 2

        period_start = cycle_start
        period_end = cycle_start + timedelta(days=period_length - 1)

        follicular_start = period_end + timedelta(days=1)
        follicular_end = cycle_start + timedelta(days=ovulation_day - 2)

        ovulation_start = cycle_start + timedelta(days=ovulation_day - 1)
        ovulation_end = ovulation_start + timedelta(days=2)

        luteal_start = ovulation_end + timedelta(days=1)
        luteal_end = cycle_start + timedelta(days=cycle_length - 1)

        phases.append(("Period", period_start, period_end))
        if follicular_start <= follicular_end:
            phases.append(("Follicular", follicular_start, follicular_end))
        phases.append(("Ovulation", ovulation_start, ovulation_end))
        if luteal_start <= luteal_end:
            phases.append(("Luteal", luteal_start, luteal_end))

        cycle_start += timedelta(days=cycle_length)

    return phases


def adjust_previous_luteal(service, calendar_id, new_start_date):
    """Adjust the luteal phase of the previous cycle to bridge to new_start_date."""
    search_start = (new_start_date - timedelta(days=60)).isoformat() + "T00:00:00Z"
    search_end = new_start_date.isoformat() + "T00:00:00Z"

    events = service.events().list(
        calendarId=calendar_id,
        timeMin=search_start,
        timeMax=search_end,
        privateExtendedProperty="cycleTracker=true",
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    luteal_event = None
    for event in events.get("items", []):
        if event.get("summary") == "Luteal":
            luteal_event = event

    if not luteal_event:
        return

    luteal_start = date.fromisoformat(luteal_event["start"]["date"])

    if luteal_start >= new_start_date:
        service.events().delete(
            calendarId=calendar_id, eventId=luteal_event["id"]
        ).execute()
        print("Removed previous luteal phase (overlapped with new period).")
    else:
        # Google all-day end is exclusive, so end=new_start_date means last day is day before
        luteal_event["end"]["date"] = new_start_date.isoformat()
        service.events().update(
            calendarId=calendar_id,
            eventId=luteal_event["id"],
            body=luteal_event,
        ).execute()
        print("Adjusted previous luteal phase.")


def delete_cycle_events(service, calendar_id, from_date, to_date=None):
    """Delete cycle events that start on or after from_date (and before to_date if given)."""
    time_min = from_date.isoformat() + "T00:00:00Z"
    page_token = None
    deleted = 0

    while True:
        params = dict(
            calendarId=calendar_id,
            timeMin=time_min,
            privateExtendedProperty="cycleTracker=true",
            pageToken=page_token,
            singleEvents=True,
            maxResults=250,
        )
        if to_date:
            params["timeMax"] = to_date.isoformat() + "T00:00:00Z"

        events = service.events().list(**params).execute()

        for event in events.get("items", []):
            event_start = event["start"].get("date")
            if not event_start:
                continue
            start = date.fromisoformat(event_start)
            if start >= from_date and (to_date is None or start < to_date):
                service.events().delete(
                    calendarId=calendar_id, eventId=event["id"]
                ).execute()
                deleted += 1

        page_token = events.get("nextPageToken")
        if not page_token:
            break

    label = f"{from_date} to {to_date}" if to_date else f"{from_date} onwards"
    print(f"Deleted {deleted} event(s) ({label}).")


def create_phase_events(service, calendar_id, phases):
    """Create all-day events for each phase on Google Calendar."""
    created = 0
    for name, start, end in phases:
        event = {
            "summary": name,
            "start": {"date": start.isoformat()},
            "end": {"date": (end + timedelta(days=1)).isoformat()},
            "colorId": PHASE_COLORS[name],
            "extendedProperties": {
                "private": {"cycleTracker": "true"}
            },
        }
        service.events().insert(calendarId=calendar_id, body=event).execute()
        created += 1
        if created % 10 == 0:
            print(f"  Created {created} events...")

    print(f"Created {created} event(s).")


def cmd_auth(_args):
    authenticate()


def cmd_sync(args):
    config = load_config()
    history = load_history()

    if args.start_date:
        try:
            start_date = date.fromisoformat(args.start_date)
        except ValueError:
            print("Invalid date format. Use YYYY-MM-DD.")
            sys.exit(1)

        start_str = start_date.isoformat()
        if start_str not in history:
            history.append(start_str)
            history.sort()
        save_history(history)
    else:
        if not history:
            print("No history yet. Use: sync --start-date YYYY-MM-DD")
            sys.exit(1)
        start_date = date.fromisoformat(history[-1])

    service = get_calendar_service()
    calendar_id = get_or_create_cycle_calendar(service)

    cycle_length = get_median_cycle_length(history, config["cycle_length_days"])
    source = "median of past cycles" if len(history) >= 2 else "config default"

    print(f"Syncing from {start_date} (cycle length: {cycle_length} days — {source})")

    delete_cycle_events(service, calendar_id, from_date=start_date)

    phases = calculate_phases(
        start_date,
        cycle_length=cycle_length,
        period_length=config["period_length_days"],
        months_ahead=config["months_ahead"],
    )
    create_phase_events(service, calendar_id, phases)
    print("Done!")


def cmd_resync(_args):
    history = load_history()
    if not history:
        print("No history yet. Use: sync --start-date YYYY-MM-DD")
        sys.exit(1)

    config = load_config()
    service = get_calendar_service()
    calendar_id = get_or_create_cycle_calendar(service)

    cycle_length = get_median_cycle_length(history, config["cycle_length_days"])
    source = "median of past cycles" if len(history) >= 2 else "config default"
    first_date = date.fromisoformat(history[0])

    print(f"Full resync (cycle length: {cycle_length} days — {source})")

    # Wipe everything
    delete_cycle_events(service, calendar_id, from_date=first_date)

    # Recreate past cycles from history (each with its actual length)
    all_phases = []
    for i, start_str in enumerate(history):
        start = date.fromisoformat(start_str)
        if i + 1 < len(history):
            next_start = date.fromisoformat(history[i + 1])
            actual_length = (next_start - start).days
        else:
            actual_length = cycle_length
        ovulation_day = actual_length // 2
        period_length = config["period_length_days"]

        period_end = start + timedelta(days=period_length - 1)
        follicular_start = period_end + timedelta(days=1)
        follicular_end = start + timedelta(days=ovulation_day - 2)
        ovulation_start = start + timedelta(days=ovulation_day - 1)
        ovulation_end = ovulation_start + timedelta(days=2)
        luteal_start = ovulation_end + timedelta(days=1)
        luteal_end = start + timedelta(days=actual_length - 1)

        all_phases.append(("Period", start, period_end))
        if follicular_start <= follicular_end:
            all_phases.append(("Follicular", follicular_start, follicular_end))
        all_phases.append(("Ovulation", ovulation_start, ovulation_end))
        if luteal_start <= luteal_end:
            all_phases.append(("Luteal", luteal_start, luteal_end))

    # Future predictions from last start date (skip first cycle, already added above)
    last_start = date.fromisoformat(history[-1])
    future_start = last_start + timedelta(days=cycle_length)
    future_phases = calculate_phases(
        future_start,
        cycle_length=cycle_length,
        period_length=config["period_length_days"],
        months_ahead=config["months_ahead"],
    )
    all_phases.extend(future_phases)

    create_phase_events(service, calendar_id, all_phases)
    print("Done!")


def cmd_clear(_args):
    service = get_calendar_service()
    calendar_id = get_or_create_cycle_calendar(service)
    print("Clearing all future cycle events...")
    delete_cycle_events(service, calendar_id, from_date=date.today())
    print("Done!")


def cmd_remove(args):
    try:
        remove_date = date.fromisoformat(args.date)
    except ValueError:
        print("Invalid date format. Use YYYY-MM-DD.")
        sys.exit(1)

    history = load_history()
    remove_str = remove_date.isoformat()

    if remove_str not in history:
        print(f"{remove_str} not found in history.")
        print(f"Tracked dates: {', '.join(history) if history else 'none'}")
        return

    idx = history.index(remove_str)
    next_date = date.fromisoformat(history[idx + 1]) if idx + 1 < len(history) else None

    service = get_calendar_service()
    calendar_id = get_or_create_cycle_calendar(service)

    # Delete calendar events for that cycle
    delete_cycle_events(service, calendar_id, from_date=remove_date, to_date=next_date)

    # If there's a previous cycle, extend its luteal to bridge the gap
    if idx > 0 and next_date:
        adjust_previous_luteal(service, calendar_id, next_date)

    # Remove from history
    history.remove(remove_str)
    save_history(history)
    print(f"Removed {remove_str} from history.")


def cmd_stats(_args):
    history = load_history()
    if len(history) < 2:
        print("Not enough data to show cycle lengths.")
        print(f"Tracked period start dates: {len(history)}")
        if history:
            print(f"  {history[0]}")
        print("Need at least 2 period start dates.")
        return

    lengths = calculate_cycle_lengths(history)
    recent_starts = history[-13:]  # last 13 starts give up to 12 cycle lengths
    recent_lengths = lengths[-12:]
    start_idx = len(history) - len(recent_starts)

    print(f"Cycle History (last {len(recent_lengths)}):")
    print("-" * 44)
    for i, length in enumerate(recent_lengths):
        idx = len(lengths) - len(recent_lengths) + i
        print(f"  {history[idx]}  →  {history[idx + 1]}  =  {length} days")
    print("-" * 44)
    median = get_median_cycle_length(history, None)
    print(f"Median cycle length: {median} days")


def main():
    parser = argparse.ArgumentParser(description="Menstrual cycle Google Calendar sync")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("auth", help="Authenticate with Google Calendar")

    sync_parser = subparsers.add_parser("sync", help="Sync cycle phases to calendar")
    sync_parser.add_argument(
        "--start-date", default=None, help="Period start date (YYYY-MM-DD). Omit to refresh from last known date."
    )

    remove_parser = subparsers.add_parser("remove", help="Remove a wrong period date")
    remove_parser.add_argument(
        "--date", required=True, help="Period start date to remove (YYYY-MM-DD)"
    )

    subparsers.add_parser("resync", help="Wipe and recreate all events from history")
    subparsers.add_parser("clear", help="Delete all future cycle events")
    subparsers.add_parser("stats", help="Show cycle length history (last 12)")

    args = parser.parse_args()

    commands = {
        "auth": cmd_auth,
        "sync": cmd_sync,
        "remove": cmd_remove,
        "resync": cmd_resync,
        "clear": cmd_clear,
        "stats": cmd_stats,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
