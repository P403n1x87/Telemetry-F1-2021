from datetime import datetime
import re

from influxdb_client import WritePrecision, InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from telemetry_f1_2021.packets import (
    PacketCarStatusData,
    PacketCarTelemetryData,
    PacketLapData,
    PacketMotionData,
    PacketSessionData,
    PacketCarDamageData,
    TYRES,
)
from telemetry_f1_2021.listener import TelemetryListener


TOKEN = "NLyjW4ml8XuTPTwCbtC5PC1Z-JJ6lwjAm7B1-ScM_XP9N_eoCkIGTmm3wHrC92cQVsMmKofgqbx6PM-ZZgVQKw=="
BUCKET = "f1-2021-telemetry"


SNAKE_CASE_RE = re.compile(r'(?<!^)(?=[A-Z])')


def _to_snake_case(name):
    return SNAKE_CASE_RE.sub('_', name).lower()


_HANDLERS = {
    cls: "handle_" + _to_snake_case(cls.__name__[6:])
    for cls in [
        PacketCarTelemetryData,
        PacketLapData,
        PacketMotionData,
        PacketSessionData,
        PacketCarStatusData,
        PacketCarDamageData,
    ]
}


def _flatten_tyre_values(data, name):
    temps = data.pop(name)
    data.update(
        {f"{name}_{tyre.name.lower()}": temp for tyre, temp in zip(TYRES, temps)}
    )


def _player_index(packet):
    return packet.m_header.m_player_car_index


class PacketHandler:
    def __init__(self, sink):
        self.sink = sink

        self.session = None
        self.lap = 0
        self.sector = 0
        self.sectors = [0, 0, 0]
        self.motion_data = None
        self.session_id = None
        self.tyre = None

    def init_session(self):
        self.session = datetime.now().strftime('%Y-%m-%d@%H:%M')

    def on_new_lap(self):
        self.tyre = None
        self.sector = 0
        self.sectors[:] = [0, 0, 0]

    def write(self, lap, fields):
        if self.session is None or not lap:
            return

        p = Point(f"{self.session}-{lap:002}")
        p._fields.update(fields)
        p.time(datetime.utcnow(), WritePrecision.MS)
        self.sink.write(bucket=BUCKET, record=p)

    def live(self, fields):
        if self.session is None:
            return

        p = Point("live")
        p._fields.update(fields)
        p.time(datetime.utcnow(), WritePrecision.MS)
        self.sink.write(bucket=BUCKET, record=p)

    def handle_session_data(self, packet):
        if self.session_id != packet.m_session_link_identifier:
            self.session_id = packet.m_session_link_identifier
            self.init_session()

    def handle_car_telemetry_data(self, packet):
        if self.motion_data is None:
            return

        data = packet.m_car_telemetry_data[_player_index(packet)].to_dict()
        data.update(self.motion_data)
        self.motion_data = None

        for k, v in dict(data).items():
            if isinstance(v, list) and len(v) == len(TYRES):
                _flatten_tyre_values(data, k)

        self.write(self.lap, data)

    def handle_car_status_data(self, packet):
        data = packet.m_car_status_data[_player_index(packet)].to_dict()
        if self.tyre is None:
            self.tyre = {16: "Soft", 17: "Medium", 18: "Hard", 7: "Inter", 8: "Wet"}[
                data["m_visual_tyre_compound"]
            ]
            self.write(
                self.lap,
                {
                    "tyre_compound": self.tyre,
                    "tyre_age": data["m_tyres_age_laps"],
                },
            )

    def handle_car_damage_data(self, packet):
        try:
            data = packet.m_car_damage_data[_player_index(packet)].to_dict()
        except IndexError:
            return

        for k, v in dict(data).items():
            if isinstance(v, list) and len(v) == len(TYRES):
                _flatten_tyre_values(data, k)

        self.live(data)

    def handle_lap_data(self, packet):
        data = packet.m_lap_data[_player_index(packet)]

        if data.m_sector != self.sector:
            self.sector = data.m_sector
            if self.sector > 0:
                sector_time = getattr(data, f"m_sector{self.sector}_time_in_ms")
                if sector_time > 0:
                    self.sectors[self.sector - 1] = sector_time

        if data.m_current_lap_num != self.lap:
            total_time = data.m_last_lap_time_in_ms
            if all(_ > 0 for _ in self.sectors[:2]):
                self.sectors[2] = total_time - sum(self.sectors)
                secs, ms = divmod(total_time, 1000)
                mins, secs = divmod(secs, 60)
                print(
                    f"Lap {self.lap}: {mins}:{secs:02}.{ms:03}",
                    [f"{_ / 1000:.03f}" for _ in self.sectors],
                )

            lap_data = {f"sector_{i+1}_ms": t for i, t in enumerate(self.sectors)}
            lap_data["total_time_ms"] = total_time

            self.write(self.lap, lap_data)

            self.on_new_lap()

        self.lap = data.m_current_lap_num

    def handle_motion_data(self, packet):
        self.motion_data = packet.m_car_motion_data[_player_index(packet)].to_dict()

    def _noop(self, packet):
        # print(f"Unhandled packet type {packet.__class__}")
        pass

    def __call__(self, packet):
        return getattr(self, _HANDLERS.get(packet.__class__, "_noop"))(packet)


def main():
    listener = TelemetryListener()
    print("Listening for telemetry data...")

    try:
        with InfluxDBClient(
            url="http://localhost:8086", token=TOKEN, org="P403n1x87", debug=False
        ) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            print("Connected to InfluxDB")

            handler = PacketHandler(write_api)
            while True:
                handler(listener.get())

    except KeyboardInterrupt:
        print("\nBox box.")


if __name__ == '__main__':
    main()
